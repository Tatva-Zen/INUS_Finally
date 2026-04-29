"""
MarketDataRouter — dispatches tickers to the correct MarketDataSource.
Owns the shared PriceCache and is the single entry point for all market data.
See planning/MARKET_INTERFACE.md for routing rules.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from .interface import MarketDataSource, PriceCache, PriceTick
from .massive import MassiveSource
from .simulator import SimulatorSource
from .yfinance_source import YFinanceSource

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MarketDataRouter:
    """
    Dispatches tickers to the correct MarketDataSource.
    Owns the shared PriceCache.

    Routing rules (from PLAN.md §7):
    1. .NS / .BO suffix  → YFinanceSource (always)
    2. US ticker + MASSIVE_API_KEY set → MassiveSource
    3. US ticker + no key → SimulatorSource
    """

    def __init__(
        self,
        simulator: SimulatorSource,
        massive: MassiveSource | None,
        yfinance: YFinanceSource,
        cache: PriceCache,
    ) -> None:
        self._simulator = simulator
        self._massive = massive
        self._yfinance = yfinance
        self.cache = cache

    @staticmethod
    def _is_indian(ticker: str) -> bool:
        upper = ticker.upper()
        return upper.endswith(".NS") or upper.endswith(".BO")

    def _source_for(self, ticker: str) -> MarketDataSource:
        if self._is_indian(ticker):
            return self._yfinance
        if self._massive is not None:
            return self._massive
        return self._simulator

    async def start_all(self) -> None:
        """Start all sources. Called once at app startup."""
        await self._simulator.start()
        if self._massive:
            await self._massive.start()
        await self._yfinance.start()
        logger.info("MarketDataRouter: all sources started")

    async def stop_all(self) -> None:
        """Gracefully stop all sources. Called at app shutdown."""
        await self._simulator.stop()
        if self._massive:
            await self._massive.stop()
        await self._yfinance.stop()
        logger.info("MarketDataRouter: all sources stopped")

    def add_ticker(self, ticker: str) -> None:
        """Route a new ticker to its source."""
        self._source_for(ticker).add_ticker(ticker)
        logger.debug("MarketDataRouter: added %s", ticker)

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from its source."""
        self._source_for(ticker).remove_ticker(ticker)
        logger.debug("MarketDataRouter: removed %s", ticker)

    def get_price(self, ticker: str) -> PriceTick | None:
        """Read the latest price from the shared cache."""
        return self.cache.get(ticker)

    def get_all_prices(self) -> list[PriceTick]:
        """Return all cached prices (both markets, all sources)."""
        return self.cache.get_all()

    def resolve_indian_ticker(self, bare_name: str) -> str | None:
        """
        Resolve a bare Indian ticker name to canonical .NS or .BO form.
        Delegates to YFinanceSource which caches results for the session.
        Returns None if unrecognised.
        """
        return self._yfinance.resolve_ticker(bare_name)


def build_router(cache: PriceCache | None = None) -> MarketDataRouter:
    """
    Factory function that creates a fully configured MarketDataRouter.
    Reads MASSIVE_API_KEY from the environment.
    Optionally accepts an existing PriceCache (useful in tests).
    """
    if cache is None:
        cache = PriceCache()

    massive_key = os.getenv("MASSIVE_API_KEY", "").strip()
    massive: MassiveSource | None = (
        MassiveSource(api_key=massive_key, cache=cache) if massive_key else None
    )
    simulator = SimulatorSource(cache=cache)
    yfinance_source = YFinanceSource(cache=cache)

    return MarketDataRouter(
        simulator=simulator,
        massive=massive,
        yfinance=yfinance_source,
        cache=cache,
    )
