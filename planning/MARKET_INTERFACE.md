# Market Data Interface — Unified Python API Design

## Purpose

This document defines the unified Python interface for retrieving stock prices in FinAlly. All market data flows through a single `MarketDataSource` abstract base class. Three concrete implementations — `SimulatorSource`, `MassiveSource`, and `YFinanceSource` — plug into a `MarketDataRouter` that dispatches each ticker to the correct source based on ticker suffix and environment configuration.

---

## Design Goals

- **Transparent routing**: callers never need to know which underlying source is active.
- **Single in-memory cache**: one `PriceCache` keyed by canonical ticker is written by background pollers and read by the SSE stream.
- **Stale-price resilience**: on source failure, the cache serves the last-known price with `stale=True`.
- **Hot-swappable**: adding a new source (e.g. a second broker) only requires implementing `MarketDataSource`.

---

## Data Model

### `PriceTick`

The unit of data flowing through the system. All sources produce this type; the SSE stream emits it.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

@dataclass
class PriceTick:
    ticker: str                              # canonical form, e.g. "AAPL" or "RELIANCE.NS"
    market: Literal["us", "in"]             # "us" or "in"
    price: float                            # latest price in native currency
    previous_price: float                   # price before this tick (for flash direction)
    currency: Literal["USD", "INR"]         # "USD" or "INR"
    timestamp: datetime                     # UTC timestamp of this tick
    stale: bool = False                     # True when source failed; serving cached value
    source: str = "unknown"                 # "simulator", "massive", "yfinance"

    @property
    def change_direction(self) -> Literal["up", "down", "flat"]:
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"
```

---

## Abstract Base Class

```python
from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    """
    Abstract interface that every price source must implement.
    Concrete classes: SimulatorSource, MassiveSource, YFinanceSource.
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start the background polling/generation loop.
        Called once at application startup.
        """

    @abstractmethod
    async def stop(self) -> None:
        """
        Gracefully stop the background loop.
        Called on application shutdown.
        """

    @abstractmethod
    def get_price(self, ticker: str) -> PriceTick | None:
        """
        Return the latest cached PriceTick for a ticker.
        Returns None if the ticker has never been seen by this source.
        """

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """
        Inform the source that it should track this ticker from now on.
        Idempotent — safe to call multiple times with the same ticker.
        """

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """
        Stop tracking a ticker.
        Idempotent — safe to call if the ticker is not tracked.
        """

    @abstractmethod
    def all_tickers(self) -> list[str]:
        """Return the list of tickers currently tracked by this source."""
```

---

## Price Cache

A single shared in-memory store. Background sources write to it; the SSE stream reads from it.

```python
import threading
from datetime import datetime

class PriceCache:
    """Thread-safe in-memory cache of the latest PriceTick per ticker."""

    def __init__(self):
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
```

---

## Market Data Router

The router is the single entry point for all market data. It owns the `PriceCache` and delegates to the correct `MarketDataSource`.

### Routing Rules (from PLAN.md §7)

1. Ticker ends in `.NS` or `.BO` → **YFinanceSource** (always, regardless of `MASSIVE_API_KEY`)
2. US ticker + `MASSIVE_API_KEY` set and non-empty → **MassiveSource**
3. US ticker + no `MASSIVE_API_KEY` → **SimulatorSource**

```python
import os
from typing import Literal

class MarketDataRouter:
    """
    Dispatches tickers to the correct MarketDataSource.
    Owns the shared PriceCache.
    """

    def __init__(
        self,
        simulator: "SimulatorSource",
        massive: "MassiveSource | None",
        yfinance: "YFinanceSource",
        cache: PriceCache,
    ):
        self._simulator = simulator
        self._massive = massive          # None when MASSIVE_API_KEY not set
        self._yfinance = yfinance
        self.cache = cache

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_indian(ticker: str) -> bool:
        return ticker.upper().endswith(".NS") or ticker.upper().endswith(".BO")

    def _source_for(self, ticker: str) -> "MarketDataSource":
        if self._is_indian(ticker):
            return self._yfinance
        if self._massive is not None:
            return self._massive
        return self._simulator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Start all sources. Called once at app startup."""
        await self._simulator.start()
        if self._massive:
            await self._massive.start()
        await self._yfinance.start()

    async def stop_all(self) -> None:
        """Gracefully stop all sources. Called at app shutdown."""
        await self._simulator.stop()
        if self._massive:
            await self._massive.stop()
        await self._yfinance.stop()

    def add_ticker(self, ticker: str) -> None:
        """Route a new ticker to its source."""
        self._source_for(ticker).add_ticker(ticker)

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from its source."""
        self._source_for(ticker).remove_ticker(ticker)

    def get_price(self, ticker: str) -> PriceTick | None:
        """Read the latest price from the shared cache."""
        return self.cache.get(ticker)

    def get_all_prices(self) -> list[PriceTick]:
        """Return all cached prices (both markets, all sources)."""
        return self.cache.get_all()
```

---

## Concrete Implementations (signatures)

Full implementations are documented in MARKET_SIMULATOR.md (simulator) and the source files themselves. Signatures shown here so the interface contract is clear.

### SimulatorSource

```python
class SimulatorSource(MarketDataSource):
    """
    Generates prices via Geometric Brownian Motion at ~500ms intervals.
    Never generates Indian tickers — routing bug if it receives one.
    Writes each new tick to the shared PriceCache.
    """

    def __init__(self, cache: PriceCache, tick_interval: float = 0.5):
        ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get_price(self, ticker: str) -> PriceTick | None: ...
    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...
    def all_tickers(self) -> list[str]: ...
```

### MassiveSource

```python
class MassiveSource(MarketDataSource):
    """
    Polls the Massive snapshot endpoint every poll_interval seconds.
    US tickers only. Never polled for .NS/.BO tickers.
    Writes new ticks to the shared PriceCache.
    """

    def __init__(
        self,
        api_key: str,
        cache: PriceCache,
        poll_interval: float = 15.0,
    ):
        ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get_price(self, ticker: str) -> PriceTick | None: ...
    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...
    def all_tickers(self) -> list[str]: ...
```

### YFinanceSource

```python
class YFinanceSource(MarketDataSource):
    """
    Polls yfinance for .NS/.BO tickers every poll_interval seconds.
    On HTTP 429 or parse failure, marks affected tickers stale and
    continues serving last-known prices.
    Writes new ticks to the shared PriceCache.
    """

    def __init__(
        self,
        cache: PriceCache,
        poll_interval: float = 15.0,
    ):
        ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get_price(self, ticker: str) -> PriceTick | None: ...
    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...
    def all_tickers(self) -> list[str]: ...

    def resolve_ticker(self, bare_name: str) -> str | None:
        """
        Resolve a bare Indian name to .NS or .BO canonical form.
        Returns None if neither exchange recognises it.
        Results are cached in memory for the session.
        """
        ...
```

---

## Dependency Injection at Startup

The router and sources are constructed once in FastAPI's `lifespan` handler and stored on `app.state`.

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()

    massive_key = os.getenv("MASSIVE_API_KEY", "").strip()
    massive = MassiveSource(api_key=massive_key, cache=cache) if massive_key else None
    simulator = SimulatorSource(cache=cache)
    yfinance_source = YFinanceSource(cache=cache)

    router = MarketDataRouter(
        simulator=simulator,
        massive=massive,
        yfinance=yfinance_source,
        cache=cache,
    )

    # Seed tickers from database watchlist + open positions
    for ticker in db.get_all_tracked_tickers():
        router.add_ticker(ticker)

    await router.start_all()
    app.state.market = router

    yield

    await router.stop_all()

app = FastAPI(lifespan=lifespan)
```

---

## SSE Streaming

The SSE endpoint reads from the shared `PriceCache` on a fixed cadence (500ms). When underlying sources are slower (Massive 15s, yfinance 15s), the cache re-emits the last-known value — `previous_price` only changes when the price actually moves, so flash animations on the frontend only fire on real changes.

```python
import asyncio
import json
from fastapi import Request
from fastapi.responses import StreamingResponse

async def price_stream(request: Request):
    router: MarketDataRouter = request.app.state.market

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            for tick in router.get_all_prices():
                data = {
                    "ticker": tick.ticker,
                    "market": tick.market,
                    "price": tick.price,
                    "previous_price": tick.previous_price,
                    "currency": tick.currency,
                    "timestamp": tick.timestamp.isoformat(),
                    "stale": tick.stale,
                    "change_direction": tick.change_direction,
                }
                yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Ticker Lifecycle

1. **User adds ticker to watchlist** → `POST /api/watchlist` → backend calls `router.add_ticker(ticker)` after writing to DB.
2. **Source receives `add_ticker`** → includes it in next poll cycle (Massive/yfinance) or starts generating (simulator).
3. **Source writes tick to cache** → `PriceCache.update(tick)`.
4. **SSE loop reads cache** → emits event to all connected clients.
5. **User removes ticker from watchlist** (and holds no position) → `router.remove_ticker(ticker)`.

Positions implicitly keep tickers tracked even after watchlist removal — the backend checks open positions before calling `remove_ticker`.

---

## File Layout

```
backend/
└── app/
    └── market/
        ├── __init__.py
        ├── interface.py      # PriceTick, MarketDataSource ABC, PriceCache
        ├── router.py         # MarketDataRouter
        ├── simulator.py      # SimulatorSource (see MARKET_SIMULATOR.md)
        ├── massive.py        # MassiveSource
        ├── yfinance.py       # YFinanceSource
        └── stream.py         # SSE endpoint
```
