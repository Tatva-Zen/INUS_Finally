# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A **market toggle** at the top (US / India) — starts on US
- A watchlist of 10 default tickers for the active market, live-updating prices in a grid
- Their wallets: **$10,000 USD** in the US wallet and **₹1,00,000 INR** in the India wallet, shown side-by-side in the header
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Switch markets** — flip between US and India via a header toggle. Watchlist, chart, heatmap, P&L chart, and positions table all switch to the active market's data. The other wallet remains visible in the header but is dormant.
- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog. Trades settle in the market's native currency against the matching wallet (USD cash buys US tickers only; INR cash buys Indian tickers only).
- **Monitor their portfolio** — per market, a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking that market's portfolio value over time
- **View a positions table** — per market: ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — the assistant operates on the currently active market (US or India) — same market selection as the UI. It can analyze that market's portfolio, execute trades, and manage that market's watchlist through natural language.
- **Manage the watchlist** — add/remove tickers manually or via the AI chat; watchlists are per-market
- **View market movers** — a separate page listing Top Gainers, Top Losers, and Most Active stocks for both US and India (see §3 Dual-Market Model and §11 Frontend Design for scope)

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Dual-Market Model

FinAlly operates **two fully independent wallets**: a US wallet (USD) and an India wallet (INR). The user toggles between them in the UI; the active market drives which watchlist, positions, heatmap, P&L chart, and chat context are shown.

### Rules

- **Two wallets, no FX**: USD buys US tickers only; INR buys Indian tickers only. No cross-currency trades, no FX conversion anywhere in the product. Cash balances, P&L, and portfolio totals are always denominated in the wallet's native currency.
- **Seeded balances**: US wallet starts at `$10,000.00`. India wallet starts at `₹1,00,000` (one lakh).
- **Market membership is by ticker suffix**: Indian tickers end in `.NS` (NSE) or `.BO` (BSE). Everything else is a US ticker. The `market` attribute on every row is derivable from the ticker but is stored explicitly for query performance (`"us"` or `"in"`).
- **Separate watchlists**: each market has its own watchlist. Adding `AAPL` never appears on the India watchlist; adding `RELIANCE.NS` never appears on the US watchlist.
- **Separate positions, trades, snapshots**: the `market` column filters every portfolio read. There is no unified "total portfolio" — the header shows two values side-by-side.
- **Single chat, active market**: the chat panel operates on the active market only. The LLM receives only that market's watchlist/positions/cash/P&L as context. Trades it proposes apply to that market. Switching markets in the UI also switches the chat's market scope (new context on next message; existing history stays visible).
- **Header**: displays both wallets side-by-side, each with cash balance and portfolio total, regardless of active market. This keeps the "dormant" wallet visible.

### Formatting

- **USD**: `$` prefix, two decimals, thousands separator. Example: `$12,345.67`.
- **INR**: `₹` prefix, Indian number grouping (2,2,3), two decimals. Example: `₹1,23,456.78`. Display rounded to whole rupees when the value exceeds `₹1,00,000` is acceptable but not required.

### Market Movers (scope)

The Top Gainers / Losers / Most Active page covers both markets on a single route, segmented by market. Details (data source, refresh cadence, layout) are in §9 (API) and §11 (Frontend). Scope/cut decision is in §14.1.

---

## 4. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 5. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic. The backend initializes the database eagerly on startup — creating tables and seeding default data if the SQLite file doesn't exist or is empty. The `/api/health` endpoint will not return healthy until initialization completes.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 6. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real US market data
# If not set, the built-in market simulator is used for US tickers
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- **US tickers** (no `.NS` / `.BO` suffix):
  - If `MASSIVE_API_KEY` is set and non-empty → Massive REST API
  - Else → built-in simulator
- **Indian tickers** (`.NS` or `.BO` suffix): **always** routed to `yfinance`, regardless of `MASSIVE_API_KEY`. The Massive client never sees Indian tickers. The simulator never generates Indian prices.
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

See §7 Market Data → Routing Precedence for the full dispatch rules.

---

## 7. Market Data

### Three Sources, One Interface

The simulator, the Massive client, and the yfinance client all implement the same abstract `MarketDataSource` interface. The backend dispatches each ticker to exactly one source based on ticker suffix and env-var configuration. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Routing Precedence

For each ticker requested by the system, the dispatch rule is:

1. If ticker ends in `.NS` or `.BO` → **yfinance**. Always. `MASSIVE_API_KEY` is irrelevant.
2. Else (US ticker, no suffix):
   - If `MASSIVE_API_KEY` is set and non-empty → **Massive**
   - Else → **Simulator**

Tickers are stored in **canonical form** (with any resolved suffix, e.g. `RELIANCE.NS`) everywhere in the database and in the SSE stream. Bare-name input (e.g. the user typing `RELIANCE` into the trade bar while on the India market) is resolved once at input time — prefer `.NS`, fall back to `.BO`, reject if neither exists — and the canonical form is what gets written to `watchlist`, `positions`, `trades`.

### Simulator (Default for US)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together) *(decoration — may be cut for v1; see Open Decisions)*
- Occasional random "events" — sudden 2-5% moves on a ticker for drama *(decoration — may be cut for v1)*
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies
- **Never generates Indian tickers.** If a `.NS`/`.BO` ticker somehow reaches the simulator, it's a routing bug.

### Massive API (Optional, US only)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all US tickers under active watchlists/positions on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the shared `PriceTick` format
- **Never polled for Indian tickers** — those go to yfinance unconditionally.

### yfinance (Indian Markets)

- Python `yfinance` library, poll-based (no stream)
- Polls the union of active `.NS`/`.BO` tickers every **15 seconds** (matches Massive free tier; tune later if needed)
- **Ticker resolution**: when the user enters a bare Indian ticker name (e.g. `RELIANCE`), probe `Ticker("RELIANCE.NS").info` first; if that fails (unknown symbol), probe `.BO`; if both fail, return an error to the caller and do not add it to the watchlist. Cache resolutions for the session so repeat lookups are free.
- **Canonical storage**: always write the resolved form (`RELIANCE.NS`) to every table.
- **Reliability**: `yfinance` scrapes Yahoo endpoints and has no SLA. On HTTP 429 or parse failure, keep serving the **last-known price** from cache with its original timestamp, and expose a per-ticker `stale: true` flag on the SSE event so the UI can render a muted state. Retry on the next poll cycle.
- **Market hours**: outside NSE/BSE trading hours, prices naturally don't change — this is fine; the SSE stream continues to emit the last-known price at the cadence below.

### Shared Price Cache

- A single background task per source writes to an in-memory price cache keyed by canonical ticker
- The cache holds: latest price, previous price, timestamp, `stale` flag, source
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server emits every ~500ms for **every ticker known to the system** (both markets, both watchlists, any held positions). When the underlying source is slower than 500ms (Massive 15s, yfinance 15s), the server re-emits the cached value — the `previous_price` still reflects the last observed change, so flash animations only fire when the price actually moves.
- Each SSE event contains: `ticker`, `market` (`"us"` or `"in"`), `price`, `previous_price`, `currency` (`"USD"` or `"INR"`), `timestamp`, `stale` (bool), `change_direction` (`"up"` | `"down"` | `"flat"`)
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 8. Database

### SQLite with Eager Initialization

The backend initializes the SQLite database on startup. If the file doesn't exist or tables are missing, it creates the schema and seeds default data before accepting any requests. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

Every portfolio-related table includes a `market` column (`"us"` or `"in"`) — this is the load-bearing way the two wallets stay separate. The schema is single-user; there is no `user_id` column (see §14.2 — decided: drop).

**users_profile** — One row per market. Holds that wallet's cash balance.
- `market` TEXT (`"us"` or `"in"`) PRIMARY KEY
- `cash_balance` REAL
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching, per market
- `id` TEXT PRIMARY KEY (UUID)
- `market` TEXT (`"us"` or `"in"`)
- `ticker` TEXT (canonical form, e.g. `AAPL` or `RELIANCE.NS`)
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(market, ticker)`

**positions** — Current holdings (one row per ticker per wallet)
- `id` TEXT PRIMARY KEY (UUID)
- `market` TEXT (`"us"` or `"in"`)
- `ticker` TEXT (canonical)
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL (in the market's native currency)
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(market, ticker)`

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `market` TEXT (`"us"` or `"in"`)
- `ticker` TEXT (canonical)
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL (in the market's native currency)
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time, per market. Recorded every 30 seconds by a background task, and immediately after each trade execution.
- `id` TEXT PRIMARY KEY (UUID)
- `market` TEXT (`"us"` or `"in"`)
- `total_value` REAL (cash + mark-to-market positions, in the market's native currency)
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM. Scoped by market because the chat operates on one wallet at a time.
- `id` TEXT PRIMARY KEY (UUID)
- `market` TEXT (`"us"` or `"in"`) — the market that was active when the message was sent
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — the subset of proposed trades/watchlist changes that were successfully executed; null for user messages and assistant messages with no actions)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- Two user-profile rows:
  - `(market="us", cash_balance=10000.00)`
  - `(market="in", cash_balance=100000.00)`
- US watchlist (10 entries): `AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX`
- India watchlist (10 entries): `RELIANCE.NS, TCS.NS, HDFCBANK.NS, INFY.NS, ICICIBANK.NS, HINDUNILVR.NS, SBIN.NS, BHARTIARTL.NS, ITC.NS, KOTAKBANK.NS`

---

## 9. API Endpoints

All portfolio/watchlist/chat endpoints take a required `market=us|in` query parameter (or body field for POST). The server rejects requests without it with `400`. The SSE price stream is global (both markets) — the client filters by `market` field per event.

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates. Emits events for all tickers in both markets; each event carries a `market` field. |
| GET | `/api/market/movers?market=us\|in` | *(Cut from MVP — v2 stretch goal; see §14.1.)* |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio?market=us\|in` | That market's positions, cash balance, total value, unrealized P&L, currency |
| POST | `/api/portfolio/trade` | Body: `{market: "us"\|"in", ticker, quantity, side}`. Server validates ticker's market matches `market`; rejects cross-market. Cash-balance check and position update run inside a single `BEGIN IMMEDIATE` SQLite transaction to prevent double-spend on concurrent requests. Returns `{trade: {...}, portfolio: {...}}` — the executed trade plus the updated portfolio snapshot (same shape as `GET /api/portfolio`). On validation failure returns `400` with `{error: "..."}`. |
| GET | `/api/portfolio/history?market=us\|in&since=<iso>&limit=<n>` | Portfolio value snapshots over time. Defaults: `since` = 24h ago, `limit` = 500 (server enforces max 5000). |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist?market=us\|in` | Snapshot of the market's watchlist tickers with latest prices. Fetched client-side after mount for initial render — thereafter the UI relies on the SSE stream. |
| POST | `/api/watchlist` | Body: `{market, ticker}`. Server resolves bare Indian tickers to canonical form (`.NS` preferred, `.BO` fallback) before writing. |
| DELETE | `/api/watchlist/{ticker}?market=us\|in` | Remove a ticker from the given market's watchlist |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chat/history?market=us\|in&limit=<n>` | Return the last `n` (default 50) chat messages for the given market, in chronological order. Used to rehydrate the chat panel on page load / market switch. |
| POST | `/api/chat` | Body: `{market, message}`. Returns the full LLM response (assistant message + executed actions). |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment) |

---

## 10. LLM Integration

When writing code to make calls to LLMs, use the `cerebras-inference` skill to call LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs are used to parse the response.

`OPENROUTER_API_KEY` is read from the project-root `.env` file.

### Scope: Active Market Only

The chat is scoped to **one market at a time** — whichever market is active in the UI when the message is sent. The LLM sees only that market's state and its actions apply only to that market. This is enforced on three sides:

- **Context**: only the active market's cash, positions, watchlist, and P&L are sent to the LLM.
- **Chat history**: only messages where `chat_messages.market = <active>` are included in the prompt.
- **Actions**: the server validates every trade/watchlist action has a ticker consistent with the active market (US tickers for US, `.NS`/`.BO` tickers for India). Cross-market actions are rejected.

### How It Works

When the user sends a chat message, the backend:

1. Loads the **active market's** portfolio context: cash, positions with current price and P&L, watchlist with live prices, portfolio total, currency label.
2. Loads the last **N messages** from `chat_messages` where `market = <active>` (see truncation policy below).
3. Constructs the prompt: system message + portfolio context + conversation history + new user message.
4. Calls the LLM via LiteLLM → OpenRouter with the JSON Schema below attached as `response_format`.
5. Parses the structured JSON response. If parsing fails, retries once; on second failure returns a "sorry, the assistant had trouble — please try again" message and logs the error.
6. Validates each proposed trade and watchlist change: market match, ticker exists (for trades), sufficient cash (buys) / shares (sells). Each action is evaluated independently — partial success is acceptable. Invalid actions are dropped and their errors are appended to the user-facing response; valid actions execute inside a single `BEGIN IMMEDIATE` transaction per chat response.
7. Persists the user message and the assistant response (with executed `actions`) to `chat_messages` with `market = <active>`.
8. Returns the response to the frontend (no token streaming — Cerebras is fast enough that a loading indicator suffices).

### Chat-History Truncation

Include the last **20 messages** (10 user + 10 assistant pairs) from the active market in each prompt. Earlier history is persisted in the DB for UI display (via `GET /api/chat/history`) but not sent to the model. This keeps prompt size bounded and deterministic regardless of session length.

### Structured Output Schema

Sent as JSON Schema via `response_format`:

```json
{
  "type": "object",
  "required": ["message"],
  "additionalProperties": false,
  "properties": {
    "message": { "type": "string" },
    "trades": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["ticker", "side", "quantity"],
        "additionalProperties": false,
        "properties": {
          "ticker":   { "type": "string" },
          "side":     { "type": "string", "enum": ["buy", "sell"] },
          "quantity": { "type": "number", "exclusiveMinimum": 0 }
        }
      }
    },
    "watchlist_changes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["ticker", "action"],
        "additionalProperties": false,
        "properties": {
          "ticker": { "type": "string" },
          "action": { "type": "string", "enum": ["add", "remove"] }
        }
      }
    }
  }
}
```

Example response (India market, buy + sell + watchlist change):

```json
{
  "message": "Rotating ₹15,000 from ITC into RELIANCE on momentum, and adding Tata Motors to the watchlist.",
  "trades": [
    {"ticker": "ITC.NS",      "side": "sell", "quantity": 100},
    {"ticker": "RELIANCE.NS", "side": "buy",  "quantity": 5}
  ],
  "watchlist_changes": [
    {"ticker": "TATAMOTORS.NS", "action": "add"}
  ]
}
```

### Validation & Error Surfacing

- **Unknown ticker** (not in the active market's universe as verified against the resolver/price cache): drop the action, append a line to the response: `Could not execute: ticker 'XYZ' was not recognized.`
- **Insufficient cash / shares**: drop the action, append: `Could not execute: insufficient <cash|shares> for <ticker>.`
- **Cross-market ticker** (e.g. `RELIANCE.NS` while active market is US): drop, append: `Could not execute: 'RELIANCE.NS' is an India ticker; you're in the US market.`
- **Upstream timeout / Cerebras 5xx**: return `{error: "assistant_unavailable"}` to the UI after a 30s hard timeout with one retry. UI shows a non-blocking toast.

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

### System Prompt Guidance

The LLM is prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven
- **Never invent tickers, prices, P&L numbers, or balances — use only the portfolio context supplied in this prompt**
- Always respond with valid JSON matching the provided schema
- You are currently operating on the **{market}** market; all your proposed trades and watchlist changes must use that market's tickers

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns a deterministic canned response instead of calling OpenRouter. This enables fast, free, reproducible E2E tests and offline development.

The mock policy:

- If the user message contains the word `buy`, return a response that buys 1 share of the first watchlist ticker of the active market.
- If the message contains `sell` and the user holds any positions in the active market, return a response that sells 1 share of the first held position.
- Otherwise, return `{"message": "Mock response — LLM is disabled (LLM_MOCK=true).", "trades": [], "watchlist_changes": []}`.

Example mock (active market = US, first watchlist entry = AAPL, user typed "please buy something"):

```json
{
  "message": "Mock: executing a test buy of 1 share of AAPL.",
  "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}],
  "watchlist_changes": []
}
```

---

## 11. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture is up to the Frontend Engineer, but the UI must include these elements:

- **Header** — always visible, always both markets:
  - **Market toggle** (US / India) — sets the active market for everything below. Default: US.
  - **Two wallet cards side-by-side**, one per market. Each shows cash balance, portfolio total, and unrealized P&L (sum of current mark-to-market value minus avg cost across all positions — the "daily P&L" label is cosmetic; the value is mark-to-market, not day-over-day), all in that market's currency with proper formatting (`$12,345.67`, `₹1,23,456.78`). The active market's card is highlighted.
  - **Connection status indicator** (green / yellow / red dot)
- **Watchlist panel** — grid/table of the **active market's** watched tickers with: ticker symbol, current price (flashing green/red on change), session change % (% change from first SSE price tick received for that ticker since page load — accumulated client-side like sparklines), sparkline mini-chart. Only shows tickers where the SSE event's `market` matches the active market.
- **Main chart area** — larger chart for the currently selected ticker (from the active market). Clicking a ticker in the watchlist selects it.
- **Portfolio heatmap** — treemap of the active market's positions, sized by portfolio weight, colored by P&L.
- **P&L chart** — line chart of the active market's portfolio value over time, using data from `portfolio_snapshots` filtered by market.
- **Positions table** — active market only: ticker, quantity, avg cost, current price, unrealized P&L, % change (all in that market's currency).
- **Trade bar** — ticker input, quantity input, Buy / Sell buttons. Trades submit against the **active market**. If the user types a ticker inconsistent with the active market (e.g. typing `AAPL` while on India), the trade bar shows a validation error inline and doesn't submit.
- **AI chat panel** — docked/collapsible sidebar, per-market history. On market switch the panel reloads via `GET /api/chat/history?market=<active>`. Loading indicator while waiting for the LLM response. Inline confirmations for trades/watchlist changes executed.
- **Market movers page** — cut from MVP (see §14.1). V2 stretch goal.

### Switching Markets

- The active-market toggle is global (e.g. persisted to `localStorage`) so reloads preserve it.
- All data-fetching hooks re-fire on switch: portfolio, watchlist, chat history, positions, P&L history. The SSE stream stays open (it carries both markets); the client simply switches its filter.
- The inactive wallet's cards keep updating in the header because SSE events for both markets keep flowing.

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Canvas-based charting library preferred (Lightweight Charts or Recharts) for performance
- Price flash effect: on receiving a new price with `change_direction !== "flat"`, apply a CSS class for ~500ms then remove it. Events marked `stale: true` render in a muted color (no flash).
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme
- Use `Intl.NumberFormat('en-US', {...USD})` and `Intl.NumberFormat('en-IN', {...INR})` for currency formatting (Indian grouping comes free with `en-IN`)

---

## 12. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a **bind mount** from the project root into the container. This matches the `db/` directory shown in §5 and keeps the DB visible to students for inspection.

```bash
docker run -v "$(pwd)/db:/app/db" -p 8000:8000 --env-file .env finally
```

On Windows PowerShell:

```powershell
docker run -v "${PWD}/db:/app/db" -p 8000:8000 --env-file .env finally
```

The backend writes `finally.db` into `/app/db/` inside the container, which is the host's `./db/finally.db`. `./db/` is gitignored but committed via `.gitkeep`.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 13. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: US watchlist of 10 appears, `$10,000.00` USD shown, India wallet also visible in header with `₹1,00,000` INR, prices are streaming
- Switch to India market: watchlist, positions, chart, heatmap, P&L, chat all swap to India data; US wallet still visible in header
- Add and remove a ticker from each market's watchlist
- Buy shares in US market: USD cash decreases, US position appears; INR wallet untouched
- Buy shares in India market: INR cash decreases, India position appears; USD wallet untouched
- Attempt a cross-market trade (`AAPL` while active market = India): UI validation error, no DB write
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors for active market, P&L chart has data points for active market
- AI chat (mocked, US market): send "buy", mock buys 1 AAPL, trade execution appears inline
- AI chat (mocked, India market): send "buy", mock buys 1 RELIANCE.NS
- SSE resilience: disconnect and verify reconnection

---

## 14. Open Decisions

Items still needing your call before implementation starts. Each has a specific question and my recommended default — strike through or override as you prefer.

### 14.1 Market Movers page: ~~keep or cut?~~ **DECIDED: cut from MVP**

Cut. Free-tier Massive has no scanner endpoint; `yfinance` movers are flaky. The feature is orthogonal to the portfolio workflow. §9 and §11 updated to reflect this. V2 stretch goal.

### 14.2 Drop `user_id` column everywhere? **DECIDED: drop**

Dropped. There is no auth model; multi-user would require a breaking migration regardless. Schema in §8 updated to remove `user_id` from all tables.

### 14.3 Drop `portfolio_snapshots` table + 30s background task?

The P&L chart reads from this table. Alternative: accumulate the P&L line **client-side** during the session (same progressive approach already accepted for sparklines). Trade-offs:
- **Keep as-is**: P&L chart survives a page reload; minor background task runs; 2,880 rows/day/market accumulate.
- **Drop**: simpler (one fewer table, one fewer endpoint, one fewer background task); P&L chart starts empty on each page load and fills as the session goes.

**My recommendation:** keep for now. It's a demo feature where "persistent P&L history" is genuinely valuable, and the overhead is trivial.

### 14.4 LLM: structured JSON vs. native tool calling?

Currently the plan uses the model's structured-output mode with a JSON Schema (see §10). The alternative is native tool calling: expose `execute_trade` and `modify_watchlist` as tools, let the model invoke them.

**My recommendation:** stick with structured JSON. Reasons:
- `openrouter/openai/gpt-oss-120b` via Cerebras has well-documented JSON-schema support.
- Tool-call support through OpenRouter + Cerebras for this specific model is less battle-tested — worth one early spike to confirm either way before committing.
- Structured JSON is one round-trip, one parse — simpler to mock for E2E.

Worth a half-day spike before the real LLM integration starts — if structured outputs are flaky on this route, swap to tool calls.

### 14.5 Four platform scripts vs. single `docker compose`?

§12 defines `start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1`. An alternative is just:

```bash
docker compose up -d    # all platforms
docker compose down     # all platforms
```

**My recommendation:** keep a thin Mac/Linux `start.sh` + Windows `start.ps1` that each just exec `docker compose up -d` and then print the URL (and optionally open a browser), plus matching `stop.*`. Two files instead of four, still pedagogically a "one command to run". The scripts become a 5-line wrapper around compose.

### 14.6 Drop AWS App Runner Terraform stretch goal?

§12 mentions "A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal". It's not part of the build but invites scope creep.

**My recommendation:** remove from PLAN.md, park in a separate `FUTURE.md` if you want to remember it.

### 14.7 Trim simulator "correlated moves" and "event spikes"?

§7 Simulator lists correlated moves (tech stocks move together) and random 2–5% event spikes. They're decorative. Plain per-ticker GBM at 500ms is already visually lively and behaves predictably.

**My recommendation:** cut both for v1 — keep plain GBM. Add drama later if the UI feels flat.

### 14.8 CLAUDE.md references stale files — **RESOLVED**

`CLAUDE.md` has been updated to remove the references to `planning/MARKET_DATA_SUMMARY.md` and `planning/archive/` (both deleted). The description now correctly reflects that the full platform is still to be built.

---

*End of plan.*
