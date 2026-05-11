from fastapi import APIRouter
from .health import router as health_router
from .stream import router as stream_router
from .portfolio import router as portfolio_router
from .watchlist import router as watchlist_router
from .chat import router as chat_router

router = APIRouter()
router.include_router(health_router)
router.include_router(stream_router)
router.include_router(portfolio_router)
router.include_router(watchlist_router)
router.include_router(chat_router)
