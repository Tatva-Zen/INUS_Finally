# Market Simulator — Design and Implementation

## Purpose

The simulator generates realistic-looking US stock prices when no `MASSIVE_API_KEY` is configured. It uses **Geometric Brownian Motion (GBM)** — the same stochastic process used in the Black-Scholes model — to produce price paths that look natural: prices drift, fluctuate, never go negative, and react continuously.

The simulator runs as an in-process asyncio background task at ~500ms intervals. It writes `PriceTick` objects to the shared `PriceCache` via the `MarketDataSource` interface. It never generates prices for Indian tickers (`.NS`/`.BO`) — those are routed to `YFinanceSource`.

---

## Geometric Brownian Motion

For a single ticker, each price step is:

```
S(t + dt) = S(t) * exp((μ - σ²/2) * dt + σ * √dt * Z)
```

where:
- `S(t)` — current price
- `μ` (mu) — annualised drift (expected return)
- `σ` (sigma) — annualised volatility
- `dt` — time step in years (`0.5 / (252 * 6.5 * 3600)` for a 500ms tick)
- `Z` — standard normal random variable `N(0,1)`

Per-tick `dt` for a 500ms interval:

```python
import math

SECONDS_PER_TRADING_YEAR = 252 * 6.5 * 3600  # ~5,896,800
TICK_INTERVAL = 0.5                            # seconds
DT = TICK_INTERVAL / SECONDS_PER_TRADING_YEAR  # ~8.48e-8
```

---

## Seed Prices and Parameters

Seed prices are chosen to approximate real-world levels as of early 2025. Parameters are per-ticker to reflect different volatility profiles.

```python
from dataclasses import dataclass

@dataclass
class TickerConfig:
    seed_price: float    # starting price in USD
    mu: float            # annualised drift (e.g. 0.10 = 10% annual return)
    sigma: float         # annualised volatility (e.g. 0.30 = 30% annual vol)

# Default US watchlist tickers
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

# Default config for any ticker not in the table above
DEFAULT_CONFIG = TickerConfig(seed_price=100.00, mu=0.10, sigma=0.30)
```

---

## Implementation

```python
import asyncio
import math
import random
import threading
from datetime import datetime, timezone

from .interface import MarketDataSource, PriceTick, PriceCache


class SimulatorSource(MarketDataSource):
    """
    Generates US stock prices via Geometric Brownian Motion at ~500ms intervals.
    Implements MarketDataSource — see MARKET_INTERFACE.md for the full contract.
    """

    TICK_INTERVAL: float = 0.5  # seconds between price updates
    SECONDS_PER_YEAR: float = 252 * 6.5 * 3600
    DT: float = TICK_INTERVAL / SECONDS_PER_YEAR

    def __init__(self, cache: PriceCache, tick_interval: float = 0.5):
        self._cache = cache
        self._tick_interval = tick_interval
        self._prices: dict[str, float] = {}      # current price per ticker
        self._configs: dict[str, TickerConfig] = {}
        self._tickers: set[str] = set()
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # MarketDataSource interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

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

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        with self._lock:
            self._tickers.discard(ticker)
            self._prices.pop(ticker, None)
            self._configs.pop(ticker, None)

    def all_tickers(self) -> list[str]:
        with self._lock:
            return list(self._tickers)

    # ------------------------------------------------------------------
    # Internal — GBM tick generation
    # ------------------------------------------------------------------

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
        dt = self._tick_interval / self.SECONDS_PER_YEAR
        log_return = (cfg.mu - 0.5 * cfg.sigma ** 2) * dt + cfg.sigma * math.sqrt(dt) * z
        new_price = current * math.exp(log_return)
        new_price = max(new_price, 0.01)  # price floor — GBM is theoretically positive but guard against float underflow

        with self._lock:
            if ticker in self._tickers:
                self._prices[ticker] = new_price

        return new_price
```

---

## GBM Math — Worked Example

For `TSLA` with `sigma=0.60` and `dt = 8.48e-8` years:

```
log_return = (0.08 - 0.5 * 0.36) * 8.48e-8 + 0.60 * sqrt(8.48e-8) * Z
           ≈ -1.0e-8 + 0.60 * 2.91e-4 * Z
           ≈ 1.75e-4 * Z          (drift term negligible at this timescale)
```

At `Z = 1.0` (one standard deviation move), price changes by `~0.017%` per tick. Over a simulated trading day (47,174 ticks ≈ 6.5 hours × 3600s / 0.5s), TSLA's annualised vol of 60% is preserved.

---

## Adding New Tickers at Runtime

`add_ticker` is thread-safe and takes effect on the next tick loop iteration. When a user adds a new ticker to their watchlist:

1. Backend calls `router.add_ticker(ticker)`.
2. Router delegates to `SimulatorSource.add_ticker(ticker)`.
3. Simulator initialises the ticker at its seed price (or `$100.00` if unknown).
4. On the next 500ms tick, a `PriceTick` appears in the cache.
5. SSE stream picks it up and pushes it to connected clients.

---

## Design Decisions

### Plain GBM — no correlated moves or event spikes (v1)

Per PLAN.md §14.7, correlated moves and random event spikes are cut for v1. Plain per-ticker GBM is visually lively and behaves predictably in tests. The `TickerConfig` struct leaves room to add a correlation matrix later if desired.

### In-process asyncio task

The simulator runs as a single `asyncio.Task` — no threads, no subprocesses. It uses `random.gauss` (which releases the GIL) and `asyncio.sleep` so it does not block the FastAPI event loop.

The shared `_prices` dict is protected by a `threading.Lock` because `add_ticker`/`remove_ticker` can be called from any thread (e.g. an API request handler), while `_run` runs on the asyncio event loop.

### Price floor

GBM prices are theoretically positive but floating-point underflow can produce 0.0 in extreme scenarios. A `max(price, 0.01)` guard is applied at every step.

### Seed price reset on restart

Each time the container starts, prices reset to `seed_price`. This is intentional — the simulator is a demo tool, not a persistent simulation. Users who want continuity should use the Massive API or yfinance.

---

## Testing the Simulator

```python
import asyncio
from unittest.mock import patch

async def test_simulator_generates_prices():
    cache = PriceCache()
    sim = SimulatorSource(cache=cache, tick_interval=0.01)  # fast for tests
    sim.add_ticker("AAPL")

    await sim.start()
    await asyncio.sleep(0.05)  # let a few ticks run
    await sim.stop()

    tick = cache.get("AAPL")
    assert tick is not None
    assert tick.market == "us"
    assert tick.currency == "USD"
    assert tick.price > 0
    assert tick.source == "simulator"


async def test_gbm_price_is_positive():
    """Price must remain positive across 10,000 simulated ticks."""
    cache = PriceCache()
    sim = SimulatorSource(cache=cache, tick_interval=0.0)
    sim.add_ticker("TSLA")

    # Drive the GBM directly rather than through the async loop
    for _ in range(10_000):
        price = sim._next_price("TSLA")
        assert price > 0


async def test_add_remove_ticker():
    cache = PriceCache()
    sim = SimulatorSource(cache=cache)
    sim.add_ticker("AAPL")
    assert "AAPL" in sim.all_tickers()
    sim.remove_ticker("AAPL")
    assert "AAPL" not in sim.all_tickers()


async def test_indian_ticker_raises():
    cache = PriceCache()
    sim = SimulatorSource(cache=cache)
    try:
        sim.add_ticker("RELIANCE.NS")
        assert False, "Should have raised"
    except ValueError:
        pass
```

---

## File Location

```
backend/
└── app/
    └── market/
        └── simulator.py   # SimulatorSource — this implementation
```

See also:
- `MARKET_INTERFACE.md` — abstract base class, `PriceTick`, `PriceCache`, routing
- `MASSIVE_API.md` — Massive and yfinance API reference with code examples
