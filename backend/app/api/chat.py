from __future__ import annotations
import asyncio
import logging
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_db_conn, get_market
from ..db.queries import (
    get_chat_history, save_chat_message,
    get_portfolio, get_watchlist, execute_trade, record_portfolio_snapshot,
    add_to_watchlist, remove_from_watchlist,
)
from ..db.init_db import get_db as _get_db
from ..llm import process_chat_message
from ..market.router import MarketDataRouter

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_MARKETS = {"us", "in"}


def _validate_market(market: str):
    if market not in VALID_MARKETS:
        raise HTTPException(400, "market must be 'us' or 'in'")


def _build_portfolio_context(portfolio: dict, watchlist: list[dict], market_router: MarketDataRouter) -> dict:
    """Build the portfolio context dict for the LLM."""
    cash = portfolio["cash_balance"]
    positions = portfolio["positions"]
    currency = portfolio["currency"]

    enriched_positions = []
    pos_value = 0.0
    for pos in positions:
        tick = market_router.get_price(pos["ticker"])
        current_price = tick.price if tick else pos["avg_cost"]
        pnl = pos["quantity"] * (current_price - pos["avg_cost"])
        pos_value += pos["quantity"] * current_price
        enriched_positions.append({
            "ticker": pos["ticker"],
            "quantity": pos["quantity"],
            "avg_cost": pos["avg_cost"],
            "current_price": current_price,
            "unrealized_pnl": pnl,
        })

    enriched_watchlist = []
    for item in watchlist:
        tick = market_router.get_price(item["ticker"])
        enriched_watchlist.append({
            "ticker": item["ticker"],
            "price": tick.price if tick else None,
        })

    return {
        "cash_balance": cash,
        "currency": currency,
        "total_value": cash + pos_value,
        "positions": enriched_positions,
        "watchlist": enriched_watchlist,
    }


@router.get("/chat/history")
async def chat_history(
    market: str,
    limit: int = 50,
    db: aiosqlite.Connection = Depends(get_db_conn),
):
    _validate_market(market)
    return await get_chat_history(db, market, limit=limit)


class ChatRequest(BaseModel):
    market: str
    message: str


@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: aiosqlite.Connection = Depends(get_db_conn),
    market_router: MarketDataRouter = Depends(get_market),
):
    _validate_market(body.market)
    market = body.market

    # Load context
    portfolio = await get_portfolio(db, market)
    watchlist = await get_watchlist(db, market)
    history = await get_chat_history(db, market, limit=20)

    portfolio_context = _build_portfolio_context(portfolio, watchlist, market_router)
    watchlist_tickers = [w["ticker"] for w in watchlist]
    positions = portfolio["positions"]

    # Save user message
    await save_chat_message(db, market, "user", body.message)

    # Call LLM (30-second timeout)
    try:
        llm_response = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: process_chat_message(
                    market=market,
                    user_message=body.message,
                    portfolio_context=portfolio_context,
                    chat_history=[{"role": m["role"], "content": m["content"]} for m in history],
                    watchlist_tickers=watchlist_tickers,
                    positions=positions,
                )
            ),
            timeout=30,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.error("LLM error: %s", exc)
        raise HTTPException(503, detail={"error": "assistant_unavailable"})

    # Execute proposed actions
    executed_trades = []
    executed_watchlist = []
    error_notes = []

    for trade_item in llm_response.get("trades", []):
        try:
            t_ticker = trade_item["ticker"].strip().upper()
            t_side = trade_item["side"]
            t_qty = float(trade_item["quantity"])

            # Market validation
            is_indian = t_ticker.endswith(".NS") or t_ticker.endswith(".BO")
            if market == "us" and is_indian:
                error_notes.append(f"Could not execute: '{t_ticker}' is an India ticker; you're in the US market.")
                continue
            if market == "in" and not is_indian:
                error_notes.append(f"Could not execute: '{t_ticker}' is a US ticker; you're in the India market.")
                continue

            # Get price
            tick = market_router.get_price(t_ticker)
            if tick is None:
                error_notes.append(f"Could not execute: ticker '{t_ticker}' was not recognized.")
                continue

            trade_record = await execute_trade(db, market, t_ticker, t_side, t_qty, tick.price)
            executed_trades.append(trade_record)
        except ValueError as e:
            error_notes.append(f"Could not execute: {e}")
        except Exception as e:
            logger.error("Trade execution error: %s", e)
            error_notes.append(f"Could not execute trade for {trade_item.get('ticker', '?')}: internal error.")

    for change in llm_response.get("watchlist_changes", []):
        try:
            wl_ticker = change["ticker"].strip().upper()
            wl_action = change["action"]

            if wl_action == "add":
                await add_to_watchlist(db, market, wl_ticker)
                market_router.add_ticker(wl_ticker)
                executed_watchlist.append({"ticker": wl_ticker, "action": "add"})
            elif wl_action == "remove":
                removed = await remove_from_watchlist(db, market, wl_ticker)
                if removed:
                    executed_watchlist.append({"ticker": wl_ticker, "action": "remove"})
        except Exception as e:
            error_notes.append(f"Could not update watchlist for {change.get('ticker', '?')}: {e}")

    # Build final message
    final_message = llm_response.get("message", "")
    if error_notes:
        final_message = final_message + "\n\n" + "\n".join(error_notes)

    actions = None
    if executed_trades or executed_watchlist:
        actions = {"trades": executed_trades, "watchlist_changes": executed_watchlist}

    # Record snapshot after any trades
    if executed_trades:
        refreshed = await get_portfolio(db, market)
        pos_value = sum(
            pos["quantity"] * (market_router.get_price(pos["ticker"]).price if market_router.get_price(pos["ticker"]) else pos["avg_cost"])
            for pos in refreshed["positions"]
        )
        await record_portfolio_snapshot(db, market, refreshed["cash_balance"] + pos_value)

    # Save assistant message
    assistant_msg = await save_chat_message(db, market, "assistant", final_message, actions=actions)

    return assistant_msg
