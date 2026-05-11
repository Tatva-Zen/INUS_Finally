from __future__ import annotations

import json
import logging
import os

from .client import get_completion
from .mock import get_mock_response
from .schema import RESPONSE_SCHEMA

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant for a simulated trading workstation.
You are operating on the {market_label} market.

You have access to the user's current portfolio context below. Use ONLY the data \
provided — never invent tickers, prices, P&L numbers, or balances.

Your capabilities:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest and execute trades when the user asks
- Manage the watchlist by adding/removing tickers
- Provide concise, data-driven analysis

Rules:
- Only propose trades and watchlist changes using {market_label} market tickers
- US market: tickers have no suffix (AAPL, GOOGL, NVDA, etc.)
- India market: tickers end in .NS or .BO (RELIANCE.NS, TCS.NS, etc.)
- Never propose cross-market trades or watchlist additions
- Always respond with valid JSON matching the provided schema
- Be concise and professional
"""


def _build_context(market: str, portfolio_context: dict) -> str:
    symbol = "$" if market == "us" else "₹"
    currency = "USD" if market == "us" else "INR"
    lines = [
        f"=== PORTFOLIO CONTEXT ({market.upper()} market, {currency}) ===",
        f"Cash: {symbol}{portfolio_context.get('cash_balance', 0):,.2f}",
        f"Total value: {symbol}{portfolio_context.get('total_value', 0):,.2f}",
        "",
        "Positions:",
    ]
    positions = portfolio_context.get("positions") or []
    if positions:
        for p in positions:
            pnl = p.get("unrealized_pnl", 0) or 0
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"  {p['ticker']}: {p['quantity']} shares @ avg {symbol}{p.get('avg_cost', 0):,.2f}"
                f" | current {symbol}{p.get('current_price', 0):,.2f}"
                f" | P&L {sign}{symbol}{pnl:,.2f}"
            )
    else:
        lines.append("  (no positions)")
    lines.append("")
    lines.append("Watchlist:")
    watchlist = portfolio_context.get("watchlist") or []
    if watchlist:
        for w in watchlist:
            price = w.get("price")
            price_str = f"{symbol}{price:,.2f}" if price else "N/A"
            lines.append(f"  {w['ticker']}: {price_str}")
    else:
        lines.append("  (empty)")
    return "\n".join(lines)


def process_chat_message(
    market: str,
    user_message: str,
    portfolio_context: dict,
    chat_history: list[dict],
    watchlist_tickers: list[str],
    positions: list[dict],
) -> dict:
    """
    Call the LLM and return the parsed response dict.

    portfolio_context shape:
        {cash_balance, total_value, positions: [{ticker, quantity, avg_cost, current_price, unrealized_pnl}],
         watchlist: [{ticker, price}]}
    chat_history: list of {role, content} dicts (last 20)
    watchlist_tickers: plain list of ticker strings (for mock mode)
    positions: list of position dicts (for mock mode)

    Returns: {message, trades: [...], watchlist_changes: [...]}
    """
    if os.getenv("LLM_MOCK", "false").lower() == "true":
        return get_mock_response(market, user_message, watchlist_tickers, positions)

    market_label = "US (USD)" if market == "us" else "India (INR)"
    system_content = _SYSTEM_PROMPT.format(market_label=market_label)
    context_content = _build_context(market, portfolio_context)

    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "system", "content": context_content},
    ]
    for msg in (chat_history or [])[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = get_completion(messages, RESPONSE_SCHEMA)
            parsed = json.loads(raw)
            parsed.setdefault("trades", [])
            parsed.setdefault("watchlist_changes", [])
            return parsed
        except Exception as exc:
            last_error = exc
            logger.error("LLM attempt %d failed: %s", attempt + 1, exc)

    raise RuntimeError(f"LLM failed after 2 attempts: {last_error}") from last_error
