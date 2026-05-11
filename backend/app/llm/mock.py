def get_mock_response(
    market: str,
    user_message: str,
    watchlist_tickers: list[str],
    positions: list[dict],
) -> dict:
    msg = user_message.lower()
    if "buy" in msg and watchlist_tickers:
        first = watchlist_tickers[0]
        return {
            "message": f"Mock: executing a test buy of 1 share of {first}.",
            "trades": [{"ticker": first, "side": "buy", "quantity": 1}],
            "watchlist_changes": [],
        }
    if "sell" in msg and positions:
        first = positions[0]["ticker"]
        return {
            "message": f"Mock: executing a test sell of 1 share of {first}.",
            "trades": [{"ticker": first, "side": "sell", "quantity": 1}],
            "watchlist_changes": [],
        }
    return {
        "message": "Mock response — LLM is disabled (LLM_MOCK=true).",
        "trades": [],
        "watchlist_changes": [],
    }
