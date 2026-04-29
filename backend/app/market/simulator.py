"""
SimulatorSource — generates US stock prices via Geometric Brownian Motion.
See planning/MARKET_SIMULATOR.md for full design rationale and math.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from .interface import MarketDataSource, PriceCache, PriceTick

logger = logging.getLogger(__name__)


@dataclass
class TickerConfig:
    seed_price: float
    mu: float    # annualised drift
    sigma: float  # annualised volatility


TICKER_CONFIGS: dict[str, TickerConfig] = {
    "AAPL":  TickerConfig(seed_price=190.00, mu=0.12, sigma=0.28),
    "GOOGL": TickerConfig(seed_price=175.00, mu=0.10, sigma=0.30),
    "MSFT":  TickerConfig(seed_price=420.00, mu=0.12, sigma=0.25),
    "AMZN":  TickerConfig(seed_price=185.00, mu=0.14, sigma=0.35),
    "TSLA":  TickerConfig(seed_price=250.00, mu=0.08, sigma=0.60),
    "NVDA":  TickerConfig(seed_price=875.00, mu=0.20, sigma=0.55),
    "META":  TickerConfig(seed_price=520.00, mu=0.15, sigma=0.38),
    "JPM":   TickerConfig(seed_price=200.00, mu=0.09, sigma=0.22),
    "V":     TickerConfig(seed_price=280.00, mu=0.10, sigma=0.20),
    "NFLX":  TickerConfig(seed_price=680.00, mu=0.11, sigma=0.40),
}

DEFAULT_CONFIG = TickerConfig(seed_price=100.00, mu=0.10, sigma=0.30)

SECONDS_PER_TRADING_YEAR: float = 252 * 6.5 * 3600  # ~5,896,800


class SimulatorSource(MarketDataSource):
    """
    Generates US stock prices via Geometric Brownian Motion at ~500ms intervals.
    Never generates Indian tickers — routing bug if it receives one.
    Writes each new tick to the shared PriceCache.
    """

    def __init__(self, cache: PriceCache, tick_interval: float = 0.5) -> None:
        self._cache = cache
        self._tick_interval = tick_interval
        self._prices: dict[str, float] = {}
        self._configs: dict[str, TickerConfig] = {}
        self._tickers: set[str] = set()
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        logger.info("SimulatorSource started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SimulatorSource stopped")

    def get_price(self, ticker: str) -> PriceTick | None:
        return self._cache.get(ticker)

    def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker.endswith(".NS") or ticker.endswith(".BO"):
            raise ValueError(f"SimulatorSource must not receive Indian ticker: {ticker}")
        with self._lock:
            if ticker not in self._tickers:
                cfg = TICKER_CONFIGS.get(ticker, DEFAULT_CONFIG)
                self._configs[ticker] = cfg
                self._prices[ticker] = cfg.seed_price
                self._tickers.add(ticker)
                logger.debug("SimulatorSource: added ticker %s at seed price %.2f", ticker, cfg.seed_price)

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        with self._lock:
            self._tickers.discard(ticker)
            self._prices.pop(ticker, None)
            self._configs.pop(ticker, None)

    def all_tickers(self) -> list[str]:
        with self._lock:
            return list(self._tickers)

    async def _run(self) -> None:
        """Main simulation loop. Runs until cancelled."""
        while True:
            with self._lock:
                tickers = list(self._tickers)

            for ticker in tickers:
                new_price = self._next_price(ticker)
                if new_price is None:
                    continue
                old_tick = self._cache.get(ticker)
                previous_price = old_tick.price if old_tick else new_price
                tick = PriceTick(
                    ticker=ticker,
                    market="us",
                    price=new_price,
                    previous_price=previous_price,
                    currency="USD",
                    timestamp=datetime.now(tz=timezone.utc),
                    stale=False,
                    source="simulator",
                )
                self._cache.update(tick)

            await asyncio.sleep(self._tick_interval)

    def _next_price(self, ticker: str) -> float | None:
        """Apply one GBM step and return the new price."""
        with self._lock:
            if ticker not in self._tickers:
                return None
            cfg = self._configs[ticker]
            current = self._prices[ticker]

        z = random.gauss(0.0, 1.0)
        dt = self._tick_interval / SECONDS_PER_TRADING_YEAR
        log_return = (cfg.mu - 0.5 * cfg.sigma ** 2) * dt + cfg.sigma * math.sqrt(dt) * z
        new_price = current * math.exp(log_return)
        # GBM is theoretically positive; guard against float underflow
        new_price = max(new_price, 0.01)

        with self._lock:
            if ticker in self._tickers:
                self._prices[ticker] = new_price

        return new_price
