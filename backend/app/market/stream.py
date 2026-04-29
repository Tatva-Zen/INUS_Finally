"""
SSE streaming endpoint for live price updates.
Reads from the shared PriceCache every 500ms and emits events to all clients.
See planning/MARKET_INTERFACE.md §SSE Streaming for design notes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import Request
from fastapi.responses import StreamingResponse

from .router import MarketDataRouter

logger = logging.getLogger(__name__)

SSE_INTERVAL = 0.5  # seconds between cache sweeps


async def _event_generator(request: Request, router: MarketDataRouter) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted price events until the client disconnects."""
    while True:
        if await request.is_disconnected():
            logger.debug("SSE client disconnected")
            break

        for tick in router.get_all_prices():
            data = {
                "ticker": tick.ticker,
                "market": tick.market,
                "price": tick.price,
                "previous_price": tick.previous_price,
                "currency": tick.currency,
                "timestamp": tick.timestamp.isoformat(),
                "stale": tick.stale,
                "change_direction": tick.change_direction,
            }
            yield f"data: {json.dumps(data)}\n\n"

        await asyncio.sleep(SSE_INTERVAL)


async def price_stream(request: Request) -> StreamingResponse:
    """
    GET /api/stream/prices — SSE endpoint.
    Emits PriceTick events for every known ticker, both markets, every 500ms.
    The client filters events by the `market` field.
    """
    router: MarketDataRouter = request.app.state.market

    return StreamingResponse(
        _event_generator(request, router),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )
