from __future__ import annotations
from typing import AsyncGenerator
import aiosqlite
from fastapi import Request
from ..db.init_db import get_db as _get_db
from ..market.router import MarketDataRouter


async def get_db_conn(request: Request) -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI dependency that yields a DB connection."""
    async with _get_db() as db:
        yield db


def get_market(request: Request) -> MarketDataRouter:
    return request.app.state.market
