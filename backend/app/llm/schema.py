RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["message"],
    "additionalProperties": False,
    "properties": {
        "message": {"type": "string"},
        "trades": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ticker", "side", "quantity"],
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "number", "exclusiveMinimum": 0}
                }
            }
        },
        "watchlist_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ticker", "action"],
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "remove"]}
                }
            }
        }
    }
}
