"""
Unit tests for the FastAPI API layer.

Uses httpx.AsyncClient with the FastAPI app, overriding dependencies to inject
a temporary SQLite database and a mock MarketDataRouter.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

import aiosqlite
import httpx
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.init_db import init_db, get_db
from app.api.deps import get_db_conn, get_market
from app.market.interface import PriceTick, PriceCache
from app.market.router import MarketDataRouter, build_router


# ---------------------------------------------------------------------------
# Helpers — mock market router
# ---------------------------------------------------------------------------

def _make_price_tick(ticker: str, price: float, market: str = "us") -> PriceTick:
    currency = "USD" if market == "us" else "INR"
    return PriceTick(
        ticker=ticker,
        market=market,
        price=price,
        previous_price=price - 1.0,
        currency=currency,
        timestamp=datetime.utcnow(),
        stale=False,
        source="mock",
    )


def _make_mock_router(prices: dict[str, float] | None = None) -> MarketDataRouter:
    """Return a MagicMock that quacks like a MarketDataRouter."""
    prices = prices or {
        "AAPL": 190.0,
        "GOOGL": 175.0,
        "MSFT": 310.0,
        "RELIANCE.NS": 2500.0,
        "TCS.NS": 3500.0,
    }

    mock = MagicMock(spec=MarketDataRouter)

    def _get_price(ticker: str) -> PriceTick | None:
        if ticker in prices:
            market = "in" if (ticker.endswith(".NS") or ticker.endswith(".BO")) else "us"
            return _make_price_tick(ticker, prices[ticker], market)
        return None

    mock.get_price.side_effect = _get_price
    mock.get_all_prices.return_value = [
        _get_price(t) for t in prices
    ]
    mock.add_ticker.return_value = None
    mock.remove_ticker.return_value = None
    mock.resolve_indian_ticker.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "test_api.db")
    await init_db(db_path=path)
    return path


@pytest.fixture
def mock_router() -> MarketDataRouter:
    return _make_mock_router()


@pytest.fixture
async def async_client(db_path: str, mock_router: MarketDataRouter):
    """
    Yield an httpx.AsyncClient with overridden DB and market dependencies,
    and with app.state.market set so SSE and other routes work too.
    """
    # Override DB dependency
    async def _override_db():
        async with get_db(db_path=db_path) as db:
            yield db

    # Override market router dependency
    def _override_market():
        return mock_router

    app.dependency_overrides[get_db_conn] = _override_db
    app.dependency_overrides[get_market] = _override_market

    # Also set app.state.market so lifespan-dependent code doesn't crash
    app.state.market = mock_router

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. GET /api/health
# ---------------------------------------------------------------------------

async def test_health_returns_ok(async_client: AsyncClient):
    resp = await async_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. GET /api/portfolio
# ---------------------------------------------------------------------------

async def test_get_portfolio_us_shape(async_client: AsyncClient):
    resp = await async_client.get("/api/portfolio?market=us")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market"] == "us"
    assert data["currency"] == "USD"
    assert data["cash_balance"] == 10000.0
    assert isinstance(data["positions"], list)
    assert "total_value" in data
    assert "total_pnl" in data


async def test_get_portfolio_india_shape(async_client: AsyncClient):
    resp = await async_client.get("/api/portfolio?market=in")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market"] == "in"
    assert data["currency"] == "INR"
    assert data["cash_balance"] == 100000.0


async def test_get_portfolio_invalid_market(async_client: AsyncClient):
    resp = await async_client.get("/api/portfolio?market=xx")
    assert resp.status_code == 400


async def test_get_portfolio_missing_market(async_client: AsyncClient):
    resp = await async_client.get("/api/portfolio")
    assert resp.status_code == 422  # Pydantic validation error — missing query param


# ---------------------------------------------------------------------------
# 3. POST /api/portfolio/trade — validation
# ---------------------------------------------------------------------------

async def test_trade_market_mismatch_aapl_on_india(async_client: AsyncClient):
    """AAPL (US ticker) submitted to India market must return 400."""
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "in",
        "ticker": "AAPL",
        "quantity": 1,
        "side": "buy",
    })
    assert resp.status_code == 400
    assert "US ticker" in resp.json()["detail"]


async def test_trade_market_mismatch_indian_on_us(async_client: AsyncClient):
    """RELIANCE.NS (India ticker) submitted to US market must return 400."""
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "us",
        "ticker": "RELIANCE.NS",
        "quantity": 1,
        "side": "buy",
    })
    assert resp.status_code == 400
    assert "India ticker" in resp.json()["detail"]


async def test_trade_invalid_side(async_client: AsyncClient):
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "us",
        "ticker": "AAPL",
        "quantity": 1,
        "side": "hold",
    })
    assert resp.status_code == 400
    assert "buy" in resp.json()["detail"] or "sell" in resp.json()["detail"]


async def test_trade_invalid_quantity_zero(async_client: AsyncClient):
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "us",
        "ticker": "AAPL",
        "quantity": 0,
        "side": "buy",
    })
    assert resp.status_code == 400


async def test_trade_invalid_market(async_client: AsyncClient):
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "xx",
        "ticker": "AAPL",
        "quantity": 1,
        "side": "buy",
    })
    assert resp.status_code == 400


async def test_trade_buy_succeeds(async_client: AsyncClient):
    """Buy 1 AAPL at mocked price 190.0 — should succeed and return trade + portfolio."""
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "us",
        "ticker": "AAPL",
        "quantity": 1,
        "side": "buy",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "trade" in data
    assert "portfolio" in data
    trade = data["trade"]
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 1
    assert trade["price"] == 190.0
    # Cash should have decreased
    assert data["portfolio"]["cash_balance"] == pytest.approx(10000.0 - 190.0)


async def test_trade_no_price_available(async_client: AsyncClient, mock_router: MarketDataRouter):
    """Ticker with no price in cache returns 400."""
    mock_router.get_price.side_effect = lambda t: None
    resp = await async_client.post("/api/portfolio/trade", json={
        "market": "us",
        "ticker": "UNKNWN",
        "quantity": 1,
        "side": "buy",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. GET /api/portfolio/history
# ---------------------------------------------------------------------------

async def test_portfolio_history_returns_list(async_client: AsyncClient):
    resp = await async_client.get("/api/portfolio/history?market=us")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_portfolio_history_invalid_market(async_client: AsyncClient):
    resp = await async_client.get("/api/portfolio/history?market=zz")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 5. GET /api/watchlist
# ---------------------------------------------------------------------------

async def test_get_watchlist_us(async_client: AsyncClient):
    resp = await async_client.get("/api/watchlist?market=us")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 10  # 10 seeded tickers
    tickers = [item["ticker"] for item in data]
    assert "AAPL" in tickers
    assert "NVDA" in tickers
    # Each item should have price info (may be None if mock doesn't have it)
    for item in data:
        assert "ticker" in item
        assert "market" in item
        assert "price" in item


async def test_get_watchlist_india(async_client: AsyncClient):
    resp = await async_client.get("/api/watchlist?market=in")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10
    tickers = [item["ticker"] for item in data]
    assert "RELIANCE.NS" in tickers


async def test_get_watchlist_invalid_market(async_client: AsyncClient):
    resp = await async_client.get("/api/watchlist?market=bad")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. POST /api/watchlist
# ---------------------------------------------------------------------------

async def test_add_watchlist_us_ticker(async_client: AsyncClient, mock_router: MarketDataRouter):
    resp = await async_client.post("/api/watchlist", json={"market": "us", "ticker": "AMD"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AMD"
    assert data["market"] == "us"
    # Verify router.add_ticker was called
    mock_router.add_ticker.assert_called_with("AMD")


async def test_add_watchlist_indian_ticker_with_suffix(async_client: AsyncClient, mock_router: MarketDataRouter):
    # Use a ticker that is NOT already in the seeded India watchlist
    resp = await async_client.post("/api/watchlist", json={"market": "in", "ticker": "WIPRO.NS"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "WIPRO.NS"
    mock_router.add_ticker.assert_called_with("WIPRO.NS")


async def test_add_watchlist_cross_market_rejected(async_client: AsyncClient):
    """Adding RELIANCE.NS to US market should fail."""
    resp = await async_client.post("/api/watchlist", json={"market": "us", "ticker": "RELIANCE.NS"})
    assert resp.status_code == 400


async def test_add_watchlist_us_ticker_to_india_rejected(async_client: AsyncClient, mock_router: MarketDataRouter):
    """Adding a bare US ticker to India market without resolution should fail."""
    # resolve_indian_ticker returns None (can't resolve)
    mock_router.resolve_indian_ticker.return_value = None
    resp = await async_client.post("/api/watchlist", json={"market": "in", "ticker": "AAPL"})
    assert resp.status_code == 400


async def test_add_watchlist_duplicate_rejected(async_client: AsyncClient):
    """Adding an already-seeded ticker raises 400."""
    resp = await async_client.post("/api/watchlist", json={"market": "us", "ticker": "AAPL"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 7. DELETE /api/watchlist/{ticker}
# ---------------------------------------------------------------------------

async def test_delete_watchlist_existing(async_client: AsyncClient):
    resp = await async_client.delete("/api/watchlist/AAPL?market=us")
    assert resp.status_code == 200
    data = resp.json()
    assert data["removed"] == "AAPL"
    assert data["market"] == "us"


async def test_delete_watchlist_not_found(async_client: AsyncClient):
    resp = await async_client.delete("/api/watchlist/NONEXISTENT?market=us")
    assert resp.status_code == 404


async def test_delete_watchlist_invalid_market(async_client: AsyncClient):
    resp = await async_client.delete("/api/watchlist/AAPL?market=zz")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 8. GET /api/chat/history
# ---------------------------------------------------------------------------

async def test_chat_history_empty(async_client: AsyncClient):
    resp = await async_client.get("/api/chat/history?market=us")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_chat_history_invalid_market(async_client: AsyncClient):
    resp = await async_client.get("/api/chat/history?market=xx")
    assert resp.status_code == 400


async def test_chat_history_returns_messages(async_client: AsyncClient, db_path: str):
    # Pre-seed a message directly in DB
    from app.db.queries import save_chat_message
    async with get_db(db_path=db_path) as db:
        await save_chat_message(db, "us", "user", "Hello from test")

    resp = await async_client.get("/api/chat/history?market=us")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Hello from test"
    assert data[0]["role"] == "user"


# ---------------------------------------------------------------------------
# 9. POST /api/chat with LLM_MOCK=true
# ---------------------------------------------------------------------------

async def test_chat_mock_neutral_message(async_client: AsyncClient, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = await async_client.post("/api/chat", json={"market": "us", "message": "How am I doing?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert "Mock response" in data["content"]
    assert data["market"] == "us"
    assert data["actions"] is None


async def test_chat_mock_buy_executes_trade(async_client: AsyncClient, monkeypatch, mock_router: MarketDataRouter):
    """Mock mode: sending 'buy' should trigger buying first watchlist ticker (AAPL)."""
    monkeypatch.setenv("LLM_MOCK", "true")
    # Mock router has AAPL at 190.0
    resp = await async_client.post("/api/chat", json={"market": "us", "message": "please buy something"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    # Trade should have been executed
    assert data["actions"] is not None
    assert len(data["actions"]["trades"]) == 1
    assert data["actions"]["trades"][0]["ticker"] == "AAPL"
    assert data["actions"]["trades"][0]["side"] == "buy"


async def test_chat_mock_sell_no_positions(async_client: AsyncClient, monkeypatch):
    """Mock mode: 'sell' with no positions held — no trade executed but graceful response."""
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = await async_client.post("/api/chat", json={"market": "us", "message": "sell everything"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    # No positions to sell, mock returns empty trades
    # (mock logic: only returns sell if positions exist)


async def test_chat_invalid_market(async_client: AsyncClient, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = await async_client.post("/api/chat", json={"market": "xx", "message": "hello"})
    assert resp.status_code == 400


async def test_chat_mock_india_market(async_client: AsyncClient, monkeypatch, mock_router: MarketDataRouter):
    """Mock mode on India market: 'buy' buys first India watchlist ticker (RELIANCE.NS)."""
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = await async_client.post("/api/chat", json={"market": "in", "message": "buy something"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert data["market"] == "in"
    # The mock should attempt RELIANCE.NS (first India watchlist ticker)
    # It may succeed or fail depending on mock router's price for RELIANCE.NS
    # but the response must be valid
    assert "content" in data


async def test_chat_saves_user_and_assistant_messages(async_client: AsyncClient, monkeypatch, db_path: str):
    monkeypatch.setenv("LLM_MOCK", "true")
    resp = await async_client.post("/api/chat", json={"market": "us", "message": "test message"})
    assert resp.status_code == 200

    # Check both messages were persisted
    from app.db.queries import get_chat_history
    async with get_db(db_path=db_path) as db:
        history = await get_chat_history(db, "us")

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "test message"
    assert history[1]["role"] == "assistant"
