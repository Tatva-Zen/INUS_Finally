"""
YFinanceSource — polls yfinance for Indian market tickers (.NS / .BO).
See planning/MASSIVE_API.md §2 for yfinance reference.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from datetime import datetime, timezone
from typing import Optional

from .interface import MarketDataSource, PriceCache, PriceTick

logger = logging.getLogger(__name__)


class YFinanceSource(MarketDataSource):
    """
    Polls yfinance for .NS/.BO tickers every poll_interval seconds.
    On HTTP 429 or any parse failure, marks affected tickers stale and
    continues serving last-known prices.
    Writes new ticks to the shared PriceCache.
    """

    def __init__(self, cache: PriceCache, poll_interval: float = 15.0) -> None:
        self._cache = cache
        self._poll_interval = poll_interval
        self._tickers: set[str] = set()
        self._resolution_cache: dict[str, Optional[str]] = {}  # bare_name → canonical or None
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("YFinanceSource started (poll_interval=%.1fs)", self._poll_interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("YFinanceSource stopped")

    def get_price(self, ticker: str) -> PriceTick | None:
        return self._cache.get(ticker)

    def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if not (ticker.endswith(".NS") or ticker.endswith(".BO")):
            raise ValueError(f"YFinanceSource only accepts .NS/.BO tickers, got: {ticker}")
        with self._lock:
            self._tickers.add(ticker)

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        with self._lock:
            self._tickers.discard(ticker)

    def all_tickers(self) -> list[str]:
        with self._lock:
            return list(self._tickers)

    def resolve_ticker(self, bare_name: str) -> Optional[str]:
        """
        Resolve a bare Indian ticker name to .NS or .BO canonical form.
        Results are cached for the session lifetime.
        Returns None if neither exchange recognises the name.
        """
        bare_name = bare_name.upper()
        with self._lock:
            if bare_name in self._resolution_cache:
                return self._resolution_cache[bare_name]

        try:
            import yfinance as yf  # import here so tests can mock easily

            for suffix in (".NS", ".BO"):
                candidate = f"{bare_name}{suffix}"
                t = yf.Ticker(candidate)
                info = t.info
                if info.get("quoteType") not in (None, "NONE", ""):
                    with self._lock:
                        self._resolution_cache[bare_name] = candidate
                    return candidate

            with self._lock:
                self._resolution_cache[bare_name] = None
            return None

        except Exception as exc:
            logger.warning("YFinanceSource: resolution error for %s: %s", bare_name, exc)
            return None

    async def _poll_loop(self) -> None:
        """Poll yfinance for all tracked Indian tickers on cadence."""
        while True:
            with self._lock:
                tickers = list(self._tickers)

            if tickers:
                # Run the blocking yfinance call in a thread pool to avoid blocking the event loop
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._fetch_and_update, tickers
                    )
                except Exception as exc:
                    logger.warning("YFinanceSource poll error: %s", exc)
                    for ticker in tickers:
                        self._cache.mark_stale(ticker)

            await asyncio.sleep(self._poll_interval)

    def _fetch_and_update(self, tickers: list[str]) -> None:
        """Blocking yfinance download — called in executor."""
        import yfinance as yf

        now = datetime.now(tz=timezone.utc)

        try:
            if len(tickers) == 1:
                prices = self._fetch_single(tickers[0], yf)
            else:
                prices = self._fetch_batch(tickers, yf)
        except Exception as exc:
            logger.warning("YFinanceSource: fetch error — marking all stale: %s", exc)
            for ticker in tickers:
                self._cache.mark_stale(ticker)
            return

        for ticker in tickers:
            price = prices.get(ticker)
            if price is None or (isinstance(price, float) and math.isnan(price)):
                self._cache.mark_stale(ticker)
                logger.debug("YFinanceSource: no price for %s — marked stale", ticker)
                continue

            old = self._cache.get(ticker)
            previous_price = old.price if old else price
            tick = PriceTick(
                ticker=ticker,
                market="in",
                price=float(price),
                previous_price=previous_price,
                currency="INR",
                timestamp=now,
                stale=False,
                source="yfinance",
            )
            self._cache.update(tick)

    @staticmethod
    def _fetch_single(ticker: str, yf) -> dict[str, float]:
        """Fetch price for a single ticker using history."""
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="1m")
        if hist.empty:
            return {}
        price = hist["Close"].iloc[-1]
        return {ticker: float(price)}

    @staticmethod
    def _fetch_batch(tickers: list[str], yf) -> dict[str, float]:
        """Fetch prices for multiple tickers via yf.download."""
        data = yf.download(
            tickers=tickers,
            period="1d",
            interval="1m",
            progress=False,
            threads=True,
            auto_adjust=True,
        )
        if data.empty:
            return {}

        prices: dict[str, float] = {}
        close = data["Close"]

        if len(tickers) == 1:
            # Single-ticker download returns a Series, not DataFrame
            ticker = tickers[0]
            val = close.iloc[-1] if not close.empty else None
            if val is not None and not math.isnan(float(val)):
                prices[ticker] = float(val)
        else:
            last_row = close.iloc[-1]
            for ticker in tickers:
                if ticker in last_row.index:
                    val = last_row[ticker]
                    if not math.isnan(float(val)):
                        prices[ticker] = float(val)

        return prices
