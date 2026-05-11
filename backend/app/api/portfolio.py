from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .deps import get_db_conn, get_market
from ..db.queries import (
    get_portfolio as db_get_portfolio,
    execute_trade as db_execute_trade,
    get_portfolio_history,
    record_portfolio_snapshot,
)
from ..market.router import MarketDataRouter

router = APIRouter()

VALID_MARKETS = {"us", "in"}


def _validate_market(market: str):
    if market not in VALID_MARKETS:
        raise HTTPException(400, f"market must be 'us' or 'in', got '{market}'")


def _enrich_portfolio(portfolio: dict, market_router: MarketDataRouter) -> dict:
    """Add current_price, unrealized_pnl, pnl_pct to each position; compute total_value."""
    positions = portfolio["positions"]
    cash = portfolio["cash_balance"]
    market = portfolio["market"]
    currency = portfolio["currency"]

    enriched_positions = []
    pos_value = 0.0
    total_pnl = 0.0

    for pos in positions:
        tick = market_router.get_price(pos["ticker"])
        current_price = tick.price if tick else pos["avg_cost"]
        unrealized_pnl = pos["quantity"] * (current_price - pos["avg_cost"])
        pnl_pct = ((current_price - pos["avg_cost"]) / pos["avg_cost"] * 100) if pos["avg_cost"] else 0.0
        pos_value += pos["quantity"] * current_price
        total_pnl += unrealized_pnl
        enriched_positions.append({
            **pos,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
        })

    return {
        "market": market,
        "currency": currency,
        "cash_balance": cash,
        "positions": enriched_positions,
        "total_value": cash + pos_value,
        "total_pnl": total_pnl,
    }


@router.get("/portfolio")
async def get_portfolio(
    market: str,
    db: aiosqlite.Connection = Depends(get_db_conn),
    market_router: MarketDataRouter = Depends(get_market),
):
    _validate_market(market)
    portfolio = await db_get_portfolio(db, market)
    return _enrich_portfolio(portfolio, market_router)


class TradeRequest(BaseModel):
    market: str
    ticker: str
    quantity: float
    side: str  # "buy" or "sell"


@router.post("/portfolio/trade")
async def trade(
    body: TradeRequest,
    db: aiosqlite.Connection = Depends(get_db_conn),
    market_router: MarketDataRouter = Depends(get_market),
):
    _validate_market(body.market)

    if body.side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if body.quantity <= 0:
        raise HTTPException(400, "quantity must be positive")

    # Validate ticker belongs to the right market
    is_indian = body.ticker.upper().endswith(".NS") or body.ticker.upper().endswith(".BO")
    if body.market == "us" and is_indian:
        raise HTTPException(400, f"'{body.ticker}' is an India ticker; you're in the US market.")
    if body.market == "in" and not is_indian:
        raise HTTPException(400, f"'{body.ticker}' is a US ticker; you're in the India market.")

    # Get current price
    tick = market_router.get_price(body.ticker)
    if tick is None:
        # Add to market router and use a fallback price — ticker isn't being tracked yet
        market_router.add_ticker(body.ticker)
        raise HTTPException(400, f"No price available for '{body.ticker}'. Wait a moment and retry.")

    try:
        trade_record = await db_execute_trade(db, body.market, body.ticker, body.side, body.quantity, tick.price)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Record snapshot after trade
    portfolio = await db_get_portfolio(db, body.market)
    enriched = _enrich_portfolio(portfolio, market_router)
    await record_portfolio_snapshot(db, body.market, enriched["total_value"])

    return {"trade": trade_record, "portfolio": enriched}


@router.get("/portfolio/history")
async def portfolio_history(
    market: str,
    since: Optional[str] = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db_conn),
):
    _validate_market(market)
    if since is None:
        since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    limit = min(limit, 5000)
    history = await get_portfolio_history(db, market, since=since, limit=limit)
    return history
