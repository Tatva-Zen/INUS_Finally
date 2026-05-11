import uuid
import json
from datetime import datetime
import aiosqlite


def _now() -> str:
    return datetime.utcnow().isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


async def get_watchlist(db: aiosqlite.Connection, market: str) -> list[dict]:
    """Return [{id, market, ticker, added_at}] for the given market."""
    async with db.execute(
        "SELECT id, market, ticker, added_at FROM watchlist WHERE market=? ORDER BY added_at",
        (market,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def add_to_watchlist(db: aiosqlite.Connection, market: str, ticker: str) -> dict:
    """Add ticker to watchlist. Raises ValueError if already exists."""
    async with db.execute(
        "SELECT id FROM watchlist WHERE market=? AND ticker=?", (market, ticker)
    ) as cursor:
        if await cursor.fetchone():
            raise ValueError(f"{ticker} is already in the {market} watchlist")

    row_id = _uid()
    now = _now()
    await db.execute(
        "INSERT INTO watchlist (id, market, ticker, added_at) VALUES (?, ?, ?, ?)",
        (row_id, market, ticker, now),
    )
    await db.commit()
    return {"id": row_id, "market": market, "ticker": ticker, "added_at": now}


async def remove_from_watchlist(db: aiosqlite.Connection, market: str, ticker: str) -> bool:
    """Remove ticker from watchlist. Returns True if removed, False if not found."""
    async with db.execute(
        "DELETE FROM watchlist WHERE market=? AND ticker=?", (market, ticker)
    ) as cursor:
        deleted = cursor.rowcount > 0
    await db.commit()
    return deleted


async def get_cash_balance(db: aiosqlite.Connection, market: str) -> float:
    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE market=?", (market,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"No profile for market {market}")
    return row["cash_balance"]


async def get_portfolio(db: aiosqlite.Connection, market: str) -> dict:
    """Return full portfolio: cash, positions, totals."""
    cash = await get_cash_balance(db, market)
    currency = "USD" if market == "us" else "INR"

    async with db.execute(
        "SELECT id, market, ticker, quantity, avg_cost, updated_at FROM positions WHERE market=? AND quantity > 0",
        (market,),
    ) as cursor:
        rows = await cursor.fetchall()

    positions = [dict(row) for row in rows]
    return {
        "market": market,
        "currency": currency,
        "cash_balance": cash,
        "positions": positions,
    }


async def execute_trade(
    db: aiosqlite.Connection,
    market: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
) -> dict:
    """
    Execute a trade. Validates cash/shares, updates position, records trade.
    Uses BEGIN IMMEDIATE to prevent double-spend.
    Raises ValueError with descriptive message on validation failure.
    Returns the executed trade dict.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    if price <= 0:
        raise ValueError("Price must be positive")

    await db.execute("BEGIN IMMEDIATE")
    try:
        # Get current cash
        async with db.execute(
            "SELECT cash_balance FROM users_profile WHERE market=?", (market,)
        ) as cursor:
            profile_row = await cursor.fetchone()
        if not profile_row:
            raise ValueError(f"No wallet for market {market}")
        cash = profile_row["cash_balance"]

        # Get current position
        async with db.execute(
            "SELECT quantity, avg_cost FROM positions WHERE market=? AND ticker=?",
            (market, ticker),
        ) as cursor:
            pos_row = await cursor.fetchone()

        existing_qty = pos_row["quantity"] if pos_row else 0.0
        existing_avg = pos_row["avg_cost"] if pos_row else 0.0

        trade_cost = quantity * price

        if side == "buy":
            if cash < trade_cost:
                raise ValueError(
                    f"Insufficient cash: need {trade_cost:.2f}, have {cash:.2f}"
                )

            new_cash = cash - trade_cost
            new_qty = existing_qty + quantity
            new_avg = (
                (existing_qty * existing_avg + quantity * price) / new_qty
                if new_qty > 0
                else price
            )

        elif side == "sell":
            if existing_qty < quantity:
                raise ValueError(
                    f"Insufficient shares of {ticker}: need {quantity}, have {existing_qty}"
                )
            new_cash = cash + trade_cost
            new_qty = existing_qty - quantity
            new_avg = existing_avg  # avg cost unchanged on sell
        else:
            raise ValueError(f"Invalid side: {side}")

        now = _now()

        # Update cash
        await db.execute(
            "UPDATE users_profile SET cash_balance=? WHERE market=?",
            (new_cash, market),
        )

        # Update or delete position
        if new_qty > 0:
            if pos_row:
                await db.execute(
                    "UPDATE positions SET quantity=?, avg_cost=?, updated_at=? WHERE market=? AND ticker=?",
                    (new_qty, new_avg, now, market, ticker),
                )
            else:
                await db.execute(
                    "INSERT INTO positions (id, market, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (_uid(), market, ticker, new_qty, new_avg, now),
                )
        else:
            await db.execute(
                "DELETE FROM positions WHERE market=? AND ticker=?", (market, ticker)
            )

        # Record trade
        trade_id = _uid()
        await db.execute(
            "INSERT INTO trades (id, market, ticker, side, quantity, price, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade_id, market, ticker, side, quantity, price, now),
        )

        await db.commit()

        return {
            "id": trade_id,
            "market": market,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "executed_at": now,
        }
    except Exception:
        await db.rollback()
        raise


async def get_trade_history(
    db: aiosqlite.Connection, market: str, limit: int = 50
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM trades WHERE market=? ORDER BY executed_at DESC LIMIT ?",
        (market, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_portfolio_history(
    db: aiosqlite.Connection,
    market: str,
    since: str | None = None,
    limit: int = 500,
) -> list[dict]:
    limit = min(limit, 5000)
    if since:
        async with db.execute(
            "SELECT id, market, total_value, recorded_at FROM portfolio_snapshots "
            "WHERE market=? AND recorded_at >= ? ORDER BY recorded_at LIMIT ?",
            (market, since, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    else:
        async with db.execute(
            "SELECT id, market, total_value, recorded_at FROM portfolio_snapshots "
            "WHERE market=? ORDER BY recorded_at LIMIT ?",
            (market, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def record_portfolio_snapshot(
    db: aiosqlite.Connection, market: str, total_value: float
) -> None:
    await db.execute(
        "INSERT INTO portfolio_snapshots (id, market, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (_uid(), market, total_value, _now()),
    )
    await db.commit()


async def get_chat_history(
    db: aiosqlite.Connection, market: str, limit: int = 50
) -> list[dict]:
    async with db.execute(
        "SELECT id, market, role, content, actions, created_at FROM chat_messages "
        "WHERE market=? ORDER BY created_at DESC LIMIT ?",
        (market, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    result = []
    for row in reversed(list(rows)):
        d = dict(row)
        if d.get("actions"):
            try:
                d["actions"] = json.loads(d["actions"])
            except Exception:
                pass
        result.append(d)
    return result


async def save_chat_message(
    db: aiosqlite.Connection,
    market: str,
    role: str,
    content: str,
    actions=None,
) -> dict:
    msg_id = _uid()
    now = _now()
    actions_json = json.dumps(actions) if actions is not None else None
    await db.execute(
        "INSERT INTO chat_messages (id, market, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (msg_id, market, role, content, actions_json, now),
    )
    await db.commit()
    return {
        "id": msg_id,
        "market": market,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": now,
    }
