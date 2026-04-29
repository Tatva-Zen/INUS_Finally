"""
Core data model and abstract interface for all market data sources.
See planning/MARKET_INTERFACE.md for full design rationale.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class PriceTick:
    """Unit of market data flowing through the system."""

    ticker: str
    market: Literal["us", "in"]
    price: float
    previous_price: float
    currency: Literal["USD", "INR"]
    timestamp: datetime
    stale: bool = False
    source: str = "unknown"

    @property
    def change_direction(self) -> Literal["up", "down", "flat"]:
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"


class MarketDataSource(ABC):
    """
    Abstract interface every price source must implement.
    Concrete classes: SimulatorSource, MassiveSource, YFinanceSource.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the background polling/generation loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the background loop."""

    @abstractmethod
    def get_price(self, ticker: str) -> PriceTick | None:
        """Return the latest cached PriceTick for a ticker, or None."""

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Inform the source to track this ticker. Idempotent."""

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker. Idempotent."""

    @abstractmethod
    def all_tickers(self) -> list[str]:
        """Return the list of tickers currently tracked by this source."""


class PriceCache:
    """Thread-safe in-memory cache of the latest PriceTick per ticker."""

    def __init__(self) -> None:
        self._data: dict[str, PriceTick] = {}
        self._lock = threading.Lock()

    def update(self, tick: PriceTick) -> None:
        with self._lock:
            existing = self._data.get(tick.ticker)
            if existing is not None and tick.price == existing.price:
                # Price unchanged — preserve previous_price; just update timestamp
                tick = PriceTick(
                    ticker=tick.ticker,
                    market=tick.market,
                    price=tick.price,
                    previous_price=existing.previous_price,
                    currency=tick.currency,
                    timestamp=tick.timestamp,
                    stale=tick.stale,
                    source=tick.source,
                )
            self._data[tick.ticker] = tick

    def get(self, ticker: str) -> PriceTick | None:
        with self._lock:
            return self._data.get(ticker)

    def get_all(self) -> list[PriceTick]:
        with self._lock:
            return list(self._data.values())

    def mark_stale(self, ticker: str) -> None:
        """Mark a ticker's last-known price as stale (source failure)."""
        with self._lock:
            tick = self._data.get(ticker)
            if tick is not None:
                self._data[ticker] = PriceTick(
                    ticker=tick.ticker,
                    market=tick.market,
                    price=tick.price,
                    previous_price=tick.previous_price,
                    currency=tick.currency,
                    timestamp=tick.timestamp,
                    stale=True,
                    source=tick.source,
                )

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
