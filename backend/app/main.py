from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .market.router import build_router
from .market.interface import PriceCache
from .db.init_db import init_db
from .api import router as api_router

logger = logging.getLogger(__name__)


async def _snapshot_task(app: FastAPI) -> None:
    """Record portfolio snapshots every 30 seconds."""
    from .db.init_db import get_db
    from .db.queries import get_portfolio, record_portfolio_snapshot
    while True:
        await asyncio.sleep(30)
        try:
            async with get_db() as db:
                for market in ("us", "in"):
                    portfolio = await get_portfolio(db, market)
                    positions = portfolio["positions"]
                    cash = portfolio["cash_balance"]
                    # Compute total value using live prices
                    pos_value = 0.0
                    for pos in positions:
                        tick = app.state.market.get_price(pos["ticker"])
                        pos_value += pos["quantity"] * (tick.price if tick else pos["avg_cost"])
                    total = cash + pos_value
                    await record_portfolio_snapshot(db, market, total)
        except Exception as exc:
            logger.error("Snapshot task error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    await init_db()

    # Build and start market data router
    cache = PriceCache()
    router = build_router(cache=cache)
    app.state.market = router

    # Seed market data router with all watchlist tickers
    from .db.init_db import get_db
    from .db.queries import get_watchlist, get_portfolio
    async with get_db() as db:
        for market in ("us", "in"):
            wl = await get_watchlist(db, market)
            for item in wl:
                router.add_ticker(item["ticker"])
            portfolio = await get_portfolio(db, market)
            for pos in portfolio["positions"]:
                router.add_ticker(pos["ticker"])

    await router.start_all()

    # Start snapshot background task
    task = asyncio.create_task(_snapshot_task(app))

    logger.info("FinAlly backend started")
    yield

    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await router.stop_all()


app = FastAPI(title="FinAlly API", lifespan=lifespan)

# API routes (must be before static files)
app.include_router(api_router, prefix="/api")

# Serve frontend static files
# In Docker: /app/static; in dev: ../frontend/out
static_dirs = [
    Path("/app/static"),
    Path(__file__).parent.parent.parent / "frontend" / "out",
]
static_dir = next((d for d in static_dirs if d.exists()), None)
if static_dir:
    # Mount static assets (Next.js _next directory, etc.)
    if (static_dir / "_next").exists():
        app.mount("/_next", StaticFiles(directory=str(static_dir / "_next")), name="next_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """Serve Next.js static export. Handles trailingSlash: true routing."""
        # Try exact file
        target = static_dir / full_path
        if target.is_file():
            return FileResponse(str(target))
        # Try with .html extension (Next.js export)
        html_target = static_dir / (full_path.rstrip("/") + ".html") if full_path else None
        if html_target and html_target.is_file():
            return FileResponse(str(html_target))
        # Try index.html in directory
        dir_index = static_dir / full_path / "index.html"
        if dir_index.is_file():
            return FileResponse(str(dir_index))
        # Fallback to root index.html
        return FileResponse(str(static_dir / "index.html"))
