# FinAlly — AI Trading Workstation

A visually stunning, AI-powered trading workstation that streams live market data, supports simulated trading across US and Indian markets, and includes an LLM chat assistant that can analyze your portfolio and execute trades on your behalf.

Built as a capstone project for an agentic AI coding course — demonstrating how orchestrated AI agents can produce a production-quality full-stack application.

---

## Features

- **Dual-market**: toggle between US (USD) and India (INR) wallets — independent watchlists, positions, and P&L
- **Live prices**: real-time streaming via SSE, with green/red flash animations on price changes
- **Simulated trading**: market orders, instant fill, no fees — $10,000 USD and ₹1,00,000 INR to start
- **Portfolio dashboard**: heatmap (treemap), P&L chart, positions table — all per active market
- **AI chat assistant**: analyze your portfolio and execute trades via natural language (powered by Cerebras/OpenRouter)
- **Sparklines**: per-ticker mini-charts built progressively from the live stream
- **Dark terminal aesthetic**: Bloomberg-inspired, desktop-first layout

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (TypeScript, static export), Tailwind CSS |
| Backend | FastAPI (Python, uv), SQLite |
| Streaming | Server-Sent Events (SSE) |
| Market data | Simulator (default), Massive API (US, optional), yfinance (India) |
| AI | LiteLLM → OpenRouter → Cerebras (`openai/gpt-oss-120b`) |
| Deployment | Single Docker container, port 8000 |

## Quick Start

### Prerequisites

- Docker
- (Optional) [OpenRouter API key](https://openrouter.ai) for AI chat
- (Optional) Massive API key for live US market data

### Setup

```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

### Run

**macOS / Linux**
```bash
./scripts/start_mac.sh
```

**Windows (PowerShell)**
```powershell
./scripts/start_windows.ps1
```

Then open [http://localhost:8000](http://localhost:8000).

### Stop

```bash
./scripts/stop_mac.sh        # macOS/Linux
./scripts/stop_windows.ps1   # Windows
```

## Environment Variables

```bash
OPENROUTER_API_KEY=   # Required for AI chat
MASSIVE_API_KEY=      # Optional: enables live US market data (else simulator)
LLM_MOCK=false        # Set true for deterministic responses in tests
```

## Project Structure

```
finally/
├── frontend/          # Next.js TypeScript app (static export)
├── backend/           # FastAPI uv project
│   └── db/            # Schema definitions and seed logic
├── db/                # Runtime SQLite volume mount (finally.db gitignored)
├── scripts/           # Start/stop Docker wrappers
├── test/              # Playwright E2E tests
├── planning/          # Architecture docs and agent reference
│   └── PLAN.md        # Full project specification
├── Dockerfile
└── docker-compose.yml
```

## Markets

| Market | Currency | Starting Balance | Data Source |
|--------|----------|-----------------|-------------|
| US | USD | $10,000.00 | Simulator or Massive API |
| India | INR | ₹1,00,000 | yfinance (NSE/BSE) |

Indian tickers use `.NS` (NSE) or `.BO` (BSE) suffixes (e.g. `RELIANCE.NS`). Bare names are resolved automatically.

## Development

See [`planning/PLAN.md`](planning/PLAN.md) for the full architecture, API reference, database schema, and design decisions.
# INUS_Finally
