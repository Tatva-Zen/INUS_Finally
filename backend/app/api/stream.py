from fastapi import APIRouter, Request
from ..market.stream import price_stream

router = APIRouter()


@router.get("/stream/prices")
async def stream_prices(request: Request):
    return await price_stream(request)
