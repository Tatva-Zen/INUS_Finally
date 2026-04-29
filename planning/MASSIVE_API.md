# Massive API (formerly Polygon.io) and yfinance — Research & Code Examples

## Overview

FinAlly uses two external data sources for market prices:

1. **Massive API** (formerly Polygon.io) — for US equities when `MASSIVE_API_KEY` is set
2. **yfinance** — exclusively for Indian market tickers (`.NS` / `.BO`)

The simulator is the default US source when no API key is provided.

---

## 1. Massive API (formerly Polygon.io)

### Background

Polygon.io rebranded as **Massive** in October 2025. All existing API keys continue to work. The Python package is `massive` (previously `polygon-api-client`).

### Installation

```bash
pip install massive
```

### Authentication

API key passed at client construction. Read from the `MASSIVE_API_KEY` environment variable.

```python
from massive import StocksClient

client = StocksClient(api_key="YOUR_MASSIVE_API_KEY")
```

### Rate Limits

| Tier      | Rate Limit         | Data Freshness          | Cost          |
|-----------|--------------------|-------------------------|---------------|
| Free      | 5 requests/minute  | End-of-day only         | $0/month      |
| Starter   | ~15 req/min        | 15-minute delayed       | ~$100/month   |
| Developer | Unlimited          | Real-time               | ~$200/month   |
| Advanced  | Unlimited          | Real-time + tick data   | ~$500/month   |

FinAlly targets the **free tier** as the baseline: poll every 15 seconds (4 calls/minute), well under the 5/minute cap.

### Key Endpoints

#### Snapshot — all tickers, single call

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,GOOGL
```

Returns the latest bid/ask, day OHLCV, and previous close for the requested tickers in one response. This is the **recommended approach for FinAlly** — one call fetches all watched tickers at once.

```python
from massive import StocksClient

client = StocksClient(api_key="YOUR_API_KEY")

tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]

# Single call returns all tickers
snapshots = client.get_snapshot_all_tickers(
    locale="us",
    market_type="stocks",
    tickers=tickers,
)

prices = {}
for snap in snapshots:
    prices[snap.ticker] = {
        "price": snap.day.close if snap.day else snap.prev_day.close,
        "open": snap.day.open if snap.day else None,
        "high": snap.day.high if snap.day else None,
        "low": snap.day.low if snap.day else None,
        "volume": snap.day.volume if snap.day else None,
        "prev_close": snap.prev_day.close if snap.prev_day else None,
        "timestamp": snap.updated,
    }
```

#### Previous Close — single ticker

```
GET /v2/aggs/ticker/{ticker}/prev
```

```python
prev = client.get_previous_close_agg(ticker="AAPL")
for agg in prev:
    print(f"AAPL prev close: {agg.close}")
```

#### Last Trade — single ticker

```
GET /v2/last/trade/{ticker}
```

```python
trade = client.get_last_trade(ticker="AAPL")
print(f"Last price: {trade.price}, time: {trade.timestamp}")
```

#### Aggregate Bars (OHLCV history)

```
GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
```

```python
bars = client.get_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="day",
    from_="2024-01-01",
    to="2024-12-31",
)
for bar in bars:
    print(bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)
```

#### Ticker Details

```
GET /v3/reference/tickers/{ticker}
```

```python
details = client.get_ticker_details(ticker="AAPL")
print(details.name, details.market_cap, details.primary_exchange)
```

### Polling Pattern for FinAlly

Since FinAlly needs to refresh US prices every ~15 seconds for the free tier, use the snapshot endpoint in a polling loop:

```python
import asyncio
import time
from massive import StocksClient

class MassivePoller:
    def __init__(self, api_key: str, poll_interval: float = 15.0):
        self.client = StocksClient(api_key=api_key)
        self.poll_interval = poll_interval
        self._prices: dict[str, float] = {}

    async def poll_loop(self, get_tickers_fn):
        """Continuously poll prices for the tickers returned by get_tickers_fn."""
        while True:
            tickers = get_tickers_fn()  # dynamic — watchlist may change
            if tickers:
                try:
                    snapshots = self.client.get_snapshot_all_tickers(
                        locale="us",
                        market_type="stocks",
                        tickers=tickers,
                    )
                    for snap in snapshots:
                        price = None
                        if snap.min and snap.min.close:
                            price = snap.min.close  # most recent minute bar
                        elif snap.day and snap.day.close:
                            price = snap.day.close
                        elif snap.prev_day and snap.prev_day.close:
                            price = snap.prev_day.close
                        if price is not None:
                            self._prices[snap.ticker] = price
                except Exception as e:
                    # Log and continue — do not crash the poll loop
                    print(f"Massive poll error: {e}")
            await asyncio.sleep(self.poll_interval)

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)
```

### Error Handling

- **HTTP 403**: invalid or missing API key
- **HTTP 429**: rate limit exceeded — back off and retry with exponential delay
- **HTTP 5xx**: transient server error — retry after short delay
- On any error, serve the **last cached price** rather than propagating the error to clients

```python
import time

def fetch_with_retry(fn, retries=3, base_delay=2.0):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
```

---

## 2. yfinance (Indian Market Tickers)

### Background

`yfinance` is a Python wrapper around Yahoo Finance's unofficial endpoints. It is **not an official API** — it scrapes Yahoo's web endpoints. There is no API key or cost. FinAlly uses it exclusively for Indian tickers (`.NS` for NSE, `.BO` for BSE).

### Installation

```bash
pip install yfinance
```

### Indian Ticker Format

| Exchange | Suffix | Example          |
|----------|--------|------------------|
| NSE      | `.NS`  | `RELIANCE.NS`    |
| BSE      | `.BO`  | `RELIANCE.BO`    |

NSE (`.NS`) is preferred. Resolution logic: try `.NS` first; fall back to `.BO` if the ticker is unknown on NSE.

### Fetching Current Prices

#### Single ticker

```python
import yfinance as yf

ticker = yf.Ticker("RELIANCE.NS")
hist = ticker.history(period="1d")
current_price = float(hist["Close"].iloc[-1])
```

#### Multiple tickers — `yf.download` (fastest)

```python
import yfinance as yf

indian_tickers = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS",
    "INFY.NS", "ICICIBANK.NS",
]

data = yf.download(
    tickers=indian_tickers,
    period="1d",
    interval="1m",   # 1-minute bars for most recent prices
    progress=False,
    threads=True,
)

# Extract last close per ticker
latest_prices = data["Close"].iloc[-1]  # Series indexed by ticker
```

#### Batch using `Tickers` class

```python
import yfinance as yf

tickers_str = "RELIANCE.NS TCS.NS HDFCBANK.NS INFY.NS"
tickers = yf.Tickers(tickers_str)

prices = {}
for sym in tickers_str.split():
    t = tickers.tickers[sym]
    hist = t.history(period="1d")
    if not hist.empty:
        prices[sym] = float(hist["Close"].iloc[-1])
```

### Ticker Resolution for Bare Names

When a user types a bare Indian stock name (e.g. `RELIANCE`) the system must resolve it to canonical form:

```python
import yfinance as yf

def resolve_indian_ticker(bare_name: str) -> str | None:
    """
    Resolve a bare Indian ticker name to its canonical .NS or .BO form.
    Returns None if neither exchange recognises it.
    """
    for suffix in (".NS", ".BO"):
        candidate = f"{bare_name.upper()}{suffix}"
        t = yf.Ticker(candidate)
        info = t.info
        # A valid ticker returns non-empty info with a recognisable quoteType
        if info.get("quoteType") not in (None, "NONE"):
            return candidate
    return None
```

Cache resolutions in memory for the session lifetime — avoid repeated Yahoo probes for the same name.

### Historical OHLCV Data

```python
import yfinance as yf

ticker = yf.Ticker("TCS.NS")

# Daily bars for the past year
hist = ticker.history(period="1y", interval="1d")
# hist columns: Open, High, Low, Close, Volume, Dividends, Stock Splits

# Intraday (1-minute, last 7 days)
intraday = ticker.history(period="7d", interval="1m")
```

**Intraday limitation**: minute-level data is available for the **last 60 days only**.

### Ticker Metadata

```python
import yfinance as yf

t = yf.Ticker("RELIANCE.NS")
info = t.info

print(info.get("longName"))          # "Reliance Industries Limited"
print(info.get("currentPrice"))      # current market price (INR)
print(info.get("marketCap"))         # market cap in INR
print(info.get("currency"))          # "INR"
print(info.get("exchange"))          # "NSI" (NSE)
print(info.get("fiftyTwoWeekHigh"))
print(info.get("fiftyTwoWeekLow"))
```

### Rate Limits and Reliability

yfinance is a web scraper — Yahoo Finance can and does throttle it.

| Concern                   | Detail                                                        |
|---------------------------|---------------------------------------------------------------|
| Rate limit error          | `YFRateLimitError` — HTTP 429 from Yahoo                     |
| Typical safe batch size   | ≤50 tickers per `yf.download` call                           |
| Polling cadence           | 15 seconds minimum recommended; FinAlly uses this cadence    |
| Market hours              | Prices don't change outside NSE/BSE hours — normal behavior  |
| Stale flag                | FinAlly exposes `stale: true` on SSE events when Yahoo fails |

### Polling Pattern for FinAlly

```python
import asyncio
import yfinance as yf
from datetime import datetime

class YFinancePoller:
    def __init__(self, poll_interval: float = 15.0):
        self.poll_interval = poll_interval
        self._prices: dict[str, float] = {}
        self._timestamps: dict[str, datetime] = {}
        self._stale: dict[str, bool] = {}

    async def poll_loop(self, get_tickers_fn):
        """Poll Indian tickers every poll_interval seconds."""
        while True:
            tickers = get_tickers_fn()  # e.g. ["RELIANCE.NS", "TCS.NS"]
            if tickers:
                try:
                    data = yf.download(
                        tickers=tickers,
                        period="1d",
                        interval="1m",
                        progress=False,
                        threads=True,
                    )
                    closes = data["Close"].iloc[-1] if not data.empty else {}
                    now = datetime.utcnow()
                    for ticker in tickers:
                        price = closes.get(ticker)
                        if price is not None and not isinstance(price, float) or price == price:  # nan check
                            self._prices[ticker] = float(price)
                            self._timestamps[ticker] = now
                            self._stale[ticker] = False
                except Exception as e:
                    # Mark all tickers stale — serve last known price
                    for ticker in tickers:
                        self._stale[ticker] = True
                    print(f"yfinance poll error: {e}")
            await asyncio.sleep(self.poll_interval)

    def get_price(self, ticker: str) -> tuple[float | None, bool]:
        """Returns (price, is_stale)."""
        return self._prices.get(ticker), self._stale.get(ticker, False)
```

### Error Handling

```python
import yfinance as yf
import time

def safe_download(tickers: list[str], retries: int = 3) -> dict[str, float]:
    """Download latest prices with retry on rate-limit errors."""
    delay = 5.0
    for attempt in range(retries):
        try:
            data = yf.download(
                tickers=tickers,
                period="1d",
                interval="1m",
                progress=False,
                threads=True,
            )
            if data.empty:
                return {}
            closes = data["Close"].iloc[-1]
            return {t: float(closes[t]) for t in tickers if t in closes and closes[t] == closes[t]}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                raise
    return {}
```

---

## 3. Side-by-Side Comparison

| Feature                    | Massive API                         | yfinance                         |
|----------------------------|-------------------------------------|----------------------------------|
| API key required           | Yes (`MASSIVE_API_KEY`)             | No                               |
| Cost                       | Free tier: 5 req/min; paid tiers    | Free                             |
| US equities                | Yes — primary use                   | Yes, but not used in FinAlly     |
| Indian equities (.NS/.BO)  | No                                  | Yes — only source in FinAlly     |
| Real-time prices           | Developer plan+                     | Delayed ~15 min                  |
| Reliability                | High (official API, SLA)            | Low (scraper, no SLA)            |
| Batch endpoint             | Yes (snapshot all tickers)          | Yes (`yf.download`)              |
| WebSocket streaming        | Yes                                 | Yes (unofficial)                 |
| FinAlly polling cadence    | 15 seconds (free tier)              | 15 seconds                       |
| FinAlly fallback           | Simulator (no key)                  | None — always used for `.NS/.BO` |

---

## 4. Dependencies in `pyproject.toml`

```toml
[project]
dependencies = [
    "massive>=1.0.0",
    "yfinance>=0.2.50",
]
```
