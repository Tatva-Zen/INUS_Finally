"""Comprehensive tests for the database layer."""
import pytest
import aiosqlite
from pathlib import Path

from app.db.init_db import init_db, get_db
from app.db.queries import (
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    get_cash_balance,
    get_portfolio,
    execute_trade,
    get_trade_history,
    get_portfolio_history,
    record_portfolio_snapshot,
    get_chat_history,
    save_chat_message,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    """Return a path for a temporary DB file and initialise it."""
    path = str(tmp_path / "test_finally.db")
    await init_db(db_path=path)
    return path


@pytest.fixture
async def db_conn(db_path: str):
    """Yield an open aiosqlite connection with row_factory set."""
    async with get_db(db_path=db_path) as conn:
        yield conn


# ---------------------------------------------------------------------------
# 1. init_db — tables exist and seed data is present
# ---------------------------------------------------------------------------

async def test_init_db_creates_tables(db_path: str):
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            tables = {row["name"] for row in await cur.fetchall()}

    expected = {
        "users_profile", "watchlist", "positions",
        "trades", "portfolio_snapshots", "chat_messages",
    }
    assert expected.issubset(tables)


async def test_init_db_seeds_wallets(db_path: str):
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM users_profile ORDER BY market") as cur:
            rows = await cur.fetchall()

    assert len(rows) == 2
    profiles = {row["market"]: row["cash_balance"] for row in rows}
    assert profiles["us"] == 10000.0
    assert profiles["in"] == 100000.0


async def test_init_db_seeds_watchlists(db_path: str):
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT market, COUNT(*) as cnt FROM watchlist GROUP BY market"
        ) as cur:
            rows = {r["market"]: r["cnt"] for r in await cur.fetchall()}

    assert rows.get("us") == 10
    assert rows.get("in") == 10


async def test_init_db_idempotent(db_path: str):
    """Calling init_db a second time must not duplicate seed data."""
    await init_db(db_path=db_path)
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT COUNT(*) as cnt FROM users_profile") as cur:
            row = await cur.fetchone()
    assert row["cnt"] == 2


# ---------------------------------------------------------------------------
# 2. get_watchlist — returns seeded tickers
# ---------------------------------------------------------------------------

async def test_get_watchlist_us(db_conn):
    items = await get_watchlist(db_conn, "us")
    tickers = [i["ticker"] for i in items]
    assert "AAPL" in tickers
    assert "NVDA" in tickers
    assert len(tickers) == 10
    # All have the correct market
    assert all(i["market"] == "us" for i in items)


async def test_get_watchlist_in(db_conn):
    items = await get_watchlist(db_conn, "in")
    tickers = [i["ticker"] for i in items]
    assert "RELIANCE.NS" in tickers
    assert "TCS.NS" in tickers
    assert len(tickers) == 10
    assert all(i["market"] == "in" for i in items)


# ---------------------------------------------------------------------------
# 3. add_to_watchlist / remove_from_watchlist
# ---------------------------------------------------------------------------

async def test_add_to_watchlist(db_conn):
    result = await add_to_watchlist(db_conn, "us", "AMD")
    assert result["ticker"] == "AMD"
    assert result["market"] == "us"
    assert "id" in result
    assert "added_at" in result

    items = await get_watchlist(db_conn, "us")
    assert any(i["ticker"] == "AMD" for i in items)


async def test_add_to_watchlist_duplicate_raises(db_conn):
    with pytest.raises(ValueError, match="already in"):
        await add_to_watchlist(db_conn, "us", "AAPL")  # already seeded


async def test_remove_from_watchlist_existing(db_conn):
    removed = await remove_from_watchlist(db_conn, "us", "AAPL")
    assert removed is True
    items = await get_watchlist(db_conn, "us")
    assert not any(i["ticker"] == "AAPL" for i in items)


async def test_remove_from_watchlist_not_found(db_conn):
    removed = await remove_from_watchlist(db_conn, "us", "NONEXISTENT")
    assert removed is False


# ---------------------------------------------------------------------------
# 4. get_portfolio — correct structure
# ---------------------------------------------------------------------------

async def test_get_portfolio_structure(db_conn):
    portfolio = await get_portfolio(db_conn, "us")
    assert portfolio["market"] == "us"
    assert portfolio["currency"] == "USD"
    assert portfolio["cash_balance"] == 10000.0
    assert isinstance(portfolio["positions"], list)
    assert len(portfolio["positions"]) == 0  # no trades yet


async def test_get_portfolio_india_structure(db_conn):
    portfolio = await get_portfolio(db_conn, "in")
    assert portfolio["market"] == "in"
    assert portfolio["currency"] == "INR"
    assert portfolio["cash_balance"] == 100000.0


# ---------------------------------------------------------------------------
# 5. execute_trade — buy reduces cash, creates position
# ---------------------------------------------------------------------------

async def test_execute_trade_buy_creates_position(db_conn):
    trade = await execute_trade(db_conn, "us", "AAPL", "buy", 10, 150.0)
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 10
    assert trade["price"] == 150.0
    assert "id" in trade
    assert "executed_at" in trade

    portfolio = await get_portfolio(db_conn, "us")
    # cash reduced by 10 * 150 = 1500
    assert abs(portfolio["cash_balance"] - (10000.0 - 1500.0)) < 1e-6
    positions = portfolio["positions"]
    assert len(positions) == 1
    assert positions[0]["ticker"] == "AAPL"
    assert positions[0]["quantity"] == 10
    assert abs(positions[0]["avg_cost"] - 150.0) < 1e-6


async def test_execute_trade_buy_averages_cost(db_conn):
    await execute_trade(db_conn, "us", "AAPL", "buy", 10, 100.0)
    await execute_trade(db_conn, "us", "AAPL", "buy", 10, 200.0)
    portfolio = await get_portfolio(db_conn, "us")
    pos = next(p for p in portfolio["positions"] if p["ticker"] == "AAPL")
    assert pos["quantity"] == 20
    # avg cost = (10*100 + 10*200) / 20 = 150
    assert abs(pos["avg_cost"] - 150.0) < 1e-6


# ---------------------------------------------------------------------------
# 6. execute_trade — sell increases cash, reduces position
# ---------------------------------------------------------------------------

async def test_execute_trade_sell_reduces_position(db_conn):
    await execute_trade(db_conn, "us", "MSFT", "buy", 5, 300.0)
    trade = await execute_trade(db_conn, "us", "MSFT", "sell", 3, 320.0)

    assert trade["side"] == "sell"
    assert trade["quantity"] == 3

    portfolio = await get_portfolio(db_conn, "us")
    cash_spent = 5 * 300.0
    cash_received = 3 * 320.0
    expected_cash = 10000.0 - cash_spent + cash_received
    assert abs(portfolio["cash_balance"] - expected_cash) < 1e-6

    pos = next(p for p in portfolio["positions"] if p["ticker"] == "MSFT")
    assert pos["quantity"] == 2


async def test_execute_trade_sell_full_removes_position(db_conn):
    await execute_trade(db_conn, "us", "GOOGL", "buy", 4, 200.0)
    await execute_trade(db_conn, "us", "GOOGL", "sell", 4, 210.0)

    portfolio = await get_portfolio(db_conn, "us")
    assert not any(p["ticker"] == "GOOGL" for p in portfolio["positions"])


# ---------------------------------------------------------------------------
# 7. execute_trade — insufficient cash raises ValueError
# ---------------------------------------------------------------------------

async def test_execute_trade_insufficient_cash(db_conn):
    with pytest.raises(ValueError, match="Insufficient cash"):
        # Attempt to buy more than $10,000 worth
        await execute_trade(db_conn, "us", "AAPL", "buy", 1000, 100.0)


# ---------------------------------------------------------------------------
# 8. execute_trade — insufficient shares raises ValueError
# ---------------------------------------------------------------------------

async def test_execute_trade_insufficient_shares(db_conn):
    await execute_trade(db_conn, "us", "AAPL", "buy", 5, 100.0)
    with pytest.raises(ValueError, match="Insufficient shares"):
        await execute_trade(db_conn, "us", "AAPL", "sell", 10, 100.0)


async def test_execute_trade_sell_no_position(db_conn):
    with pytest.raises(ValueError, match="Insufficient shares"):
        await execute_trade(db_conn, "us", "TSLA", "sell", 1, 200.0)


# ---------------------------------------------------------------------------
# Edge cases: invalid inputs
# ---------------------------------------------------------------------------

async def test_execute_trade_invalid_quantity(db_conn):
    with pytest.raises(ValueError, match="Quantity must be positive"):
        await execute_trade(db_conn, "us", "AAPL", "buy", 0, 100.0)


async def test_execute_trade_invalid_price(db_conn):
    with pytest.raises(ValueError, match="Price must be positive"):
        await execute_trade(db_conn, "us", "AAPL", "buy", 1, 0.0)


async def test_execute_trade_invalid_side(db_conn):
    with pytest.raises(ValueError, match="Invalid side"):
        await execute_trade(db_conn, "us", "AAPL", "hold", 1, 100.0)


# ---------------------------------------------------------------------------
# 9. get_portfolio_history / record_portfolio_snapshot
# ---------------------------------------------------------------------------

async def test_record_and_get_portfolio_snapshot(db_conn):
    await record_portfolio_snapshot(db_conn, "us", 10500.0)
    await record_portfolio_snapshot(db_conn, "us", 11000.0)
    await record_portfolio_snapshot(db_conn, "in", 105000.0)

    us_history = await get_portfolio_history(db_conn, "us")
    assert len(us_history) == 2
    values = [h["total_value"] for h in us_history]
    assert 10500.0 in values
    assert 11000.0 in values
    assert all(h["market"] == "us" for h in us_history)

    in_history = await get_portfolio_history(db_conn, "in")
    assert len(in_history) == 1
    assert in_history[0]["total_value"] == 105000.0


async def test_get_portfolio_history_since_filter(db_conn):
    await record_portfolio_snapshot(db_conn, "us", 9500.0)
    # Record a second snapshot a moment later — use a future timestamp via SQL
    import asyncio
    await asyncio.sleep(0.01)
    mid_time = __import__("datetime").datetime.utcnow().isoformat()
    await asyncio.sleep(0.01)
    await record_portfolio_snapshot(db_conn, "us", 10500.0)

    history = await get_portfolio_history(db_conn, "us", since=mid_time)
    assert len(history) == 1
    assert history[0]["total_value"] == 10500.0


async def test_get_portfolio_history_limit(db_conn):
    for v in range(10):
        await record_portfolio_snapshot(db_conn, "us", float(v))
    history = await get_portfolio_history(db_conn, "us", limit=5)
    assert len(history) == 5


# ---------------------------------------------------------------------------
# 10. get_chat_history / save_chat_message
# ---------------------------------------------------------------------------

async def test_save_and_get_chat_message(db_conn):
    await save_chat_message(db_conn, "us", "user", "Hello assistant")
    await save_chat_message(db_conn, "us", "assistant", "Hi there!", actions=None)

    history = await get_chat_history(db_conn, "us")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello assistant"
    assert history[1]["role"] == "assistant"


async def test_save_chat_message_with_actions(db_conn):
    actions = [{"ticker": "AAPL", "side": "buy", "quantity": 5}]
    msg = await save_chat_message(db_conn, "us", "assistant", "Buying AAPL", actions=actions)
    assert msg["actions"] == actions

    history = await get_chat_history(db_conn, "us")
    assert history[-1]["actions"] == actions


async def test_chat_history_market_isolation(db_conn):
    await save_chat_message(db_conn, "us", "user", "US message")
    await save_chat_message(db_conn, "in", "user", "India message")

    us_history = await get_chat_history(db_conn, "us")
    in_history = await get_chat_history(db_conn, "in")

    assert all(m["market"] == "us" for m in us_history)
    assert all(m["market"] == "in" for m in in_history)
    assert len(us_history) == 1
    assert len(in_history) == 1


async def test_chat_history_chronological_order(db_conn):
    import asyncio
    await save_chat_message(db_conn, "us", "user", "first")
    await asyncio.sleep(0.01)
    await save_chat_message(db_conn, "us", "assistant", "second")
    await asyncio.sleep(0.01)
    await save_chat_message(db_conn, "us", "user", "third")

    history = await get_chat_history(db_conn, "us")
    assert history[0]["content"] == "first"
    assert history[1]["content"] == "second"
    assert history[2]["content"] == "third"


async def test_chat_history_limit(db_conn):
    for i in range(10):
        await save_chat_message(db_conn, "us", "user", f"msg {i}")
    history = await get_chat_history(db_conn, "us", limit=5)
    assert len(history) == 5


# ---------------------------------------------------------------------------
# get_trade_history
# ---------------------------------------------------------------------------

async def test_get_trade_history(db_conn):
    await execute_trade(db_conn, "us", "AAPL", "buy", 2, 150.0)
    await execute_trade(db_conn, "us", "MSFT", "buy", 1, 300.0)
    history = await get_trade_history(db_conn, "us")
    assert len(history) == 2
    tickers = {t["ticker"] for t in history}
    assert "AAPL" in tickers
    assert "MSFT" in tickers


async def test_get_trade_history_market_isolation(db_conn):
    await execute_trade(db_conn, "us", "AAPL", "buy", 1, 150.0)
    await execute_trade(db_conn, "in", "RELIANCE.NS", "buy", 1, 2500.0)
    us_history = await get_trade_history(db_conn, "us")
    in_history = await get_trade_history(db_conn, "in")
    assert all(t["market"] == "us" for t in us_history)
    assert all(t["market"] == "in" for t in in_history)


# ---------------------------------------------------------------------------
# get_cash_balance
# ---------------------------------------------------------------------------

async def test_get_cash_balance_no_profile_raises(db_conn):
    with pytest.raises(ValueError, match="No profile for market"):
        await get_cash_balance(db_conn, "xx")
