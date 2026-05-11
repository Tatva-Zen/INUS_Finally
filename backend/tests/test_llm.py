"""Tests for the LLM chat integration module."""
import pytest

from app.llm.schema import RESPONSE_SCHEMA
from app.llm.mock import get_mock_response
from app.llm.chat_handler import _build_context, process_chat_message


# ---------------------------------------------------------------------------
# 1. RESPONSE_SCHEMA structure
# ---------------------------------------------------------------------------

def test_response_schema_structure():
    assert RESPONSE_SCHEMA["type"] == "object"
    assert "message" in RESPONSE_SCHEMA["required"]
    props = RESPONSE_SCHEMA["properties"]
    assert "message" in props
    assert props["message"]["type"] == "string"
    # trades array
    assert "trades" in props
    assert props["trades"]["type"] == "array"
    trade_item = props["trades"]["items"]
    assert "ticker" in trade_item["required"]
    assert "side" in trade_item["required"]
    assert "quantity" in trade_item["required"]
    # watchlist_changes array
    assert "watchlist_changes" in props
    assert props["watchlist_changes"]["type"] == "array"
    wl_item = props["watchlist_changes"]["items"]
    assert "ticker" in wl_item["required"]
    assert "action" in wl_item["required"]


# ---------------------------------------------------------------------------
# 2-5. get_mock_response tests
# ---------------------------------------------------------------------------

def test_mock_buy_returns_buy_trade():
    result = get_mock_response(
        market="us",
        user_message="please buy something",
        watchlist_tickers=["AAPL", "GOOGL"],
        positions=[],
    )
    assert result["trades"] == [{"ticker": "AAPL", "side": "buy", "quantity": 1}]
    assert result["watchlist_changes"] == []
    assert "AAPL" in result["message"]


def test_mock_sell_with_positions_returns_sell_trade():
    positions = [{"ticker": "TSLA", "quantity": 5, "avg_cost": 200.0}]
    result = get_mock_response(
        market="us",
        user_message="sell something for me",
        watchlist_tickers=["AAPL"],
        positions=positions,
    )
    assert result["trades"] == [{"ticker": "TSLA", "side": "sell", "quantity": 1}]
    assert result["watchlist_changes"] == []
    assert "TSLA" in result["message"]


def test_mock_other_message_returns_empty_trades():
    result = get_mock_response(
        market="us",
        user_message="how is my portfolio doing?",
        watchlist_tickers=["AAPL"],
        positions=[{"ticker": "TSLA", "quantity": 5, "avg_cost": 200.0}],
    )
    assert result["trades"] == []
    assert result["watchlist_changes"] == []
    assert "Mock response" in result["message"]


def test_mock_buy_with_empty_watchlist_returns_no_trades():
    result = get_mock_response(
        market="us",
        user_message="buy something",
        watchlist_tickers=[],
        positions=[],
    )
    assert result["trades"] == []
    assert result["watchlist_changes"] == []


# ---------------------------------------------------------------------------
# 6-7. process_chat_message with LLM_MOCK=true
# ---------------------------------------------------------------------------

def test_process_chat_message_mock_buy(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    result = process_chat_message(
        market="us",
        user_message="buy AAPL please",
        portfolio_context={
            "cash_balance": 10000.0,
            "total_value": 10000.0,
            "positions": [],
            "watchlist": [{"ticker": "AAPL", "price": 190.0}],
        },
        chat_history=[],
        watchlist_tickers=["AAPL", "GOOGL"],
        positions=[],
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0]["side"] == "buy"
    assert result["trades"][0]["ticker"] == "AAPL"
    assert result["trades"][0]["quantity"] == 1


def test_process_chat_message_mock_sell(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    positions = [{"ticker": "MSFT", "quantity": 3, "avg_cost": 300.0}]
    result = process_chat_message(
        market="us",
        user_message="sell something",
        portfolio_context={
            "cash_balance": 5000.0,
            "total_value": 5900.0,
            "positions": positions,
            "watchlist": [{"ticker": "AAPL", "price": 190.0}],
        },
        chat_history=[],
        watchlist_tickers=["AAPL"],
        positions=positions,
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0]["side"] == "sell"
    assert result["trades"][0]["ticker"] == "MSFT"
    assert result["trades"][0]["quantity"] == 1


# ---------------------------------------------------------------------------
# 8-9. _build_context formatting
# ---------------------------------------------------------------------------

def test_build_context_usd_format():
    ctx = {
        "cash_balance": 10000.50,
        "total_value": 12345.67,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10,
                "avg_cost": 190.0,
                "current_price": 195.0,
                "unrealized_pnl": 50.0,
            }
        ],
        "watchlist": [{"ticker": "GOOGL", "price": 175.0}],
    }
    output = _build_context("us", ctx)
    assert "US market, USD" in output
    assert "$10,000.50" in output
    assert "$12,345.67" in output
    assert "AAPL" in output
    assert "$190.00" in output
    assert "$195.00" in output
    assert "+$50.00" in output
    assert "GOOGL" in output
    assert "$175.00" in output


def test_build_context_inr_format():
    ctx = {
        "cash_balance": 100000.0,
        "total_value": 123456.78,
        "positions": [
            {
                "ticker": "RELIANCE.NS",
                "quantity": 5,
                "avg_cost": 2500.0,
                "current_price": 2600.0,
                "unrealized_pnl": 500.0,
            }
        ],
        "watchlist": [{"ticker": "TCS.NS", "price": 3500.0}],
    }
    output = _build_context("in", ctx)
    assert "IN market, INR" in output
    assert "₹100,000.00" in output
    assert "₹123,456.78" in output
    assert "RELIANCE.NS" in output
    assert "₹2,500.00" in output
    assert "₹2,600.00" in output
    assert "+₹500.00" in output
    assert "TCS.NS" in output
    assert "₹3,500.00" in output
