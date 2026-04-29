"""
MassiveSource — polls the Massive (formerly Polygon.io) snapshot API for US tickers.
See planning/MASSIVE_API.md for API reference and polling patterns.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

import httpx

from .interface import MarketDataSource, PriceCache, PriceTick

logger = logging.getLogger(__name__)

MASSIVE_SNAPSHOT_URL = (
    "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
)


class MassiveSource(MarketDataSource):
    """
    Polls the Massive snapshot endpoint every poll_interval seconds.
    US tickers only — never polled for .NS/.BO tickers.
    Writes new ticks to the shared PriceCache.
    Falls back to last-known price with stale=True on any fetch failure.
    """

    def __init__(
        self,
        api_key: str,
        cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = cache
        self._poll_interval = poll_interval
        self._tickers: set[str] = set()
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=10.0)
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("MassiveSource started (poll_interval=%.1fs)", self._poll_interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("MassiveSource stopped")

    def get_price(self, ticker: str) -> PriceTick | None:
        return self._cache.get(ticker)

    def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker.endswith(".NS") or ticker.endswith(".BO"):
            raise ValueError(f"MassiveSource must not receive Indian ticker: {ticker}")
        with self._lock:
            self._tickers.add(ticker)

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        with self._lock:
            self._tickers.discard(ticker)

    def all_tickers(self) -> list[str]:
        with self._lock:
            return list(self._tickers)

    async def _poll_loop(self) -> None:
        """Continuously poll the Massive API snapshot endpoint."""
        while True:
            with self._lock:
                tickers = list(self._tickers)

            if tickers:
                try:
                    await self._fetch_and_update(tickers)
                except Exception as exc:
                    logger.warning("MassiveSource poll error: %s", exc)
                    for ticker in tickers:
                        self._cache.mark_stale(ticker)

            await asyncio.sleep(self._poll_interval)

    async def _fetch_and_update(self, tickers: list[str]) -> None:
        """Fetch a snapshot for all given tickers and update the cache."""
        assert self._client is not None
        params = {
            "apiKey": self._api_key,
            "tickers": ",".join(tickers),
        }
        response = await self._client.get(MASSIVE_SNAPSHOT_URL, params=params)
        response.raise_for_status()
        payload = response.json()

        now = datetime.now(tz=timezone.utc)
        results = payload.get("tickers", [])

        found: set[str] = set()
        for snap in results:
            ticker = snap.get("ticker")
            if not ticker:
                continue

            price = self._extract_price(snap)
            if price is None:
                continue

            old = self._cache.get(ticker)
            previous_price = old.price if old else price
            tick = PriceTick(
                ticker=ticker,
                market="us",
                price=price,
                previous_price=previous_price,
                currency="USD",
                timestamp=now,
                stale=False,
                source="massive",
            )
            self._cache.update(tick)
            found.add(ticker)

        # Mark tickers missing from response as stale
        for ticker in tickers:
            if ticker not in found:
                self._cache.mark_stale(ticker)
                logger.debug("MassiveSource: ticker %s missing from response — marked stale", ticker)

    @staticmethod
    def _extract_price(snap: dict) -> float | None:
        """
        Extract the best available price from a Massive snapshot dict.
        Prefers most-recent-minute close → day close → prev-day close.
        """
        # Most recent minute bar
        min_bar = snap.get("min") or {}
        if min_bar.get("c"):
            return float(min_bar["c"])

        # Current day bar
        day = snap.get("day") or {}
        if day.get("c"):
            return float(day["c"])

        # Previous day close (after-hours fallback)
        prev_day = snap.get("prevDay") or {}
        if prev_day.get("c"):
            return float(prev_day["c"])

        return None
