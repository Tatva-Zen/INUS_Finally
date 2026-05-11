import os
import aiosqlite
from contextlib import asynccontextmanager
from .schema import SCHEMA_SQL
from datetime import datetime
import uuid


def get_db_path() -> str:
    return os.getenv("DB_PATH", "db/finally.db")


async def init_db(db_path: str | None = None) -> None:
    """Create tables and seed default data if empty."""
    path = db_path or get_db_path()
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA_SQL)
        await db.commit()

        # Seed if empty
        async with db.execute("SELECT COUNT(*) FROM users_profile") as cursor:
            count = (await cursor.fetchone())[0]

        if count == 0:
            now = datetime.utcnow().isoformat()
            # Seed wallet profiles
            await db.execute(
                "INSERT INTO users_profile (market, cash_balance, created_at) VALUES (?, ?, ?)",
                ("us", 10000.0, now),
            )
            await db.execute(
                "INSERT INTO users_profile (market, cash_balance, created_at) VALUES (?, ?, ?)",
                ("in", 100000.0, now),
            )

            # Seed US watchlist
            us_tickers = [
                "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
                "NVDA", "META", "JPM", "V", "NFLX",
            ]
            for ticker in us_tickers:
                await db.execute(
                    "INSERT INTO watchlist (id, market, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), "us", ticker, now),
                )

            # Seed India watchlist
            in_tickers = [
                "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
                "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
            ]
            for ticker in in_tickers:
                await db.execute(
                    "INSERT INTO watchlist (id, market, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), "in", ticker, now),
                )

            await db.commit()


@asynccontextmanager
async def get_db(db_path: str | None = None):
    """Async context manager yielding an aiosqlite.Connection."""
    path = db_path or get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db
