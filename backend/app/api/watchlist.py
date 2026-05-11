from __future__ import annotations
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .deps import get_db_conn, get_market
from ..db.queries import get_watchlist, add_to_watchlist, remove_from_watchlist
from ..market.router import MarketDataRouter

router = APIRouter()

VALID_MARKETS = {"us", "in"}


def _validate_market(market: str):
    if market not in VALID_MARKETS:
        raise HTTPException(400, f"market must be 'us' or 'in'")


def _enrich_watchlist(items: list[dict], market_router: MarketDataRouter, market: str) -> list[dict]:
    enriched = []
    for item in items:
        tick = market_router.get_price(item["ticker"])
        enriched.append({
            **item,
            "price": tick.price if tick else None,
            "change_direction": tick.change_direction if tick else None,
            "stale": tick.stale if tick else False,
        })
    return enriched


@router.get("/watchlist")
async def get_watchlist_endpoint(
    market: str,
    db: aiosqlite.Connection = Depends(get_db_conn),
    market_router: MarketDataRouter = Depends(get_market),
):
    _validate_market(market)
    items = await get_watchlist(db, market)
    return _enrich_watchlist(items, market_router, market)


class WatchlistAddRequest(BaseModel):
    market: str
    ticker: str


@router.post("/watchlist")
async def add_watchlist(
    body: WatchlistAddRequest,
    db: aiosqlite.Connection = Depends(get_db_conn),
    market_router: MarketDataRouter = Depends(get_market),
):
    _validate_market(body.market)
    ticker = body.ticker.strip().upper()

    # Resolve Indian tickers to canonical form
    is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")
    bare = ticker.replace(".NS", "").replace(".BO", "")

    if body.market == "in" and not is_indian:
        # Try to resolve bare Indian ticker
        resolved = market_router.resolve_indian_ticker(bare)
        if resolved:
            ticker = resolved
        else:
            raise HTTPException(400, f"Could not resolve '{ticker}' to a known Indian ticker (.NS or .BO). Try appending .NS manually.")

    if body.market == "us" and is_indian:
        raise HTTPException(400, f"'{ticker}' is an India ticker; you're in the US market.")

    if body.market == "in" and not (ticker.endswith(".NS") or ticker.endswith(".BO")):
        raise HTTPException(400, f"India market tickers must end in .NS or .BO")

    try:
        item = await add_to_watchlist(db, body.market, ticker)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Start tracking this ticker in the market router
    market_router.add_ticker(ticker)

    tick = market_router.get_price(ticker)
    return {
        **item,
        "price": tick.price if tick else None,
        "change_direction": tick.change_direction if tick else None,
        "stale": tick.stale if tick else False,
    }


@router.delete("/watchlist/{ticker}")
async def remove_watchlist(
    ticker: str,
    market: str,
    db: aiosqlite.Connection = Depends(get_db_conn),
):
    _validate_market(market)
    removed = await remove_from_watchlist(db, market, ticker)
    if not removed:
        raise HTTPException(404, f"'{ticker}' not found in {market} watchlist")
    return {"removed": ticker, "market": market}
