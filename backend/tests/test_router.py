"""Tests for MarketDataRouter dispatch logic."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.interface import PriceCache, PriceTick
from app.market.massive import MassiveSource
from app.market.router import MarketDataRouter, build_router
from app.market.simulator import SimulatorSource
from app.market.yfinance_source import YFinanceSource


def _build_router_with_mocks(massive: MassiveSource | None = None) -> tuple[MarketDataRouter, SimulatorSource, MassiveSource | None, YFinanceSource, PriceCache]:
    cache = PriceCache()
    sim = MagicMock(spec=SimulatorSource)
    sim.all_tickers.return_value = []
    yf = MagicMock(spec=YFinanceSource)
    yf.all_tickers.return_value = []
    yf.resolve_ticker = MagicMock(return_value=None)
    massive_mock = massive or None
    router = MarketDataRouter(simulator=sim, massive=massive_mock, yfinance=yf, cache=cache)
    return router, sim, massive_mock, yf, cache


class TestRouterRouting:
    def test_us_ticker_routes_to_simulator_when_no_massive(self):
        router, sim, _, yf, _ = _build_router_with_mocks()
        router.add_ticker("AAPL")
        sim.add_ticker.assert_called_once_with("AAPL")
        yf.add_ticker.assert_not_called()

    def test_us_ticker_routes_to_massive_when_key_set(self):
        cache = PriceCache()
        sim = MagicMock(spec=SimulatorSource)
        yf = MagicMock(spec=YFinanceSource)
        massive = MagicMock(spec=MassiveSource)

        router = MarketDataRouter(simulator=sim, massive=massive, yfinance=yf, cache=cache)
        router.add_ticker("AAPL")

        massive.add_ticker.assert_called_once_with("AAPL")
        sim.add_ticker.assert_not_called()
        yf.add_ticker.assert_not_called()

    def test_ns_ticker_routes_to_yfinance(self):
        router, sim, _, yf, _ = _build_router_with_mocks()
        router.add_ticker("RELIANCE.NS")
        yf.add_ticker.assert_called_once_with("RELIANCE.NS")
        sim.add_ticker.assert_not_called()

    def test_bo_ticker_routes_to_yfinance(self):
        router, sim, _, yf, _ = _build_router_with_mocks()
        router.add_ticker("RELIANCE.BO")
        yf.add_ticker.assert_called_once_with("RELIANCE.BO")
        sim.add_ticker.assert_not_called()

    def test_remove_us_ticker_delegates_to_simulator(self):
        router, sim, _, yf, _ = _build_router_with_mocks()
        router.remove_ticker("AAPL")
        sim.remove_ticker.assert_called_once_with("AAPL")

    def test_remove_indian_ticker_delegates_to_yfinance(self):
        router, sim, _, yf, _ = _build_router_with_mocks()
        router.remove_ticker("RELIANCE.NS")
        yf.remove_ticker.assert_called_once_with("RELIANCE.NS")

    def test_is_indian_ns(self):
        assert MarketDataRouter._is_indian("RELIANCE.NS") is True

    def test_is_indian_bo(self):
        assert MarketDataRouter._is_indian("RELIANCE.BO") is True

    def test_is_indian_us(self):
        assert MarketDataRouter._is_indian("AAPL") is False

    def test_is_indian_case_insensitive(self):
        assert MarketDataRouter._is_indian("reliance.ns") is True


class TestRouterCache:
    def test_get_price_reads_from_cache(self):
        cache = PriceCache()
        tick = PriceTick(
            ticker="AAPL", market="us", price=190.0, previous_price=189.0,
            currency="USD", timestamp=datetime.now(tz=timezone.utc), source="simulator"
        )
        cache.update(tick)

        router, _, _, _, _ = _build_router_with_mocks()
        router.cache = cache  # inject populated cache

        result = router.get_price("AAPL")
        assert result is not None
        assert result.price == 190.0

    def test_get_price_missing_returns_none(self):
        router, _, _, _, _ = _build_router_with_mocks()
        assert router.get_price("UNKNOWN") is None

    def test_get_all_prices(self):
        cache = PriceCache()
        for ticker, price in [("AAPL", 190.0), ("RELIANCE.NS", 2500.0)]:
            cache.update(PriceTick(
                ticker=ticker, market="us" if ticker == "AAPL" else "in",
                price=price, previous_price=price - 1,
                currency="USD" if ticker == "AAPL" else "INR",
                timestamp=datetime.now(tz=timezone.utc), source="test"
            ))

        router, _, _, _, _ = _build_router_with_mocks()
        router.cache = cache

        all_prices = router.get_all_prices()
        assert len(all_prices) == 2
        tickers = {t.ticker for t in all_prices}
        assert "AAPL" in tickers
        assert "RELIANCE.NS" in tickers


class TestRouterLifecycle:
    @pytest.mark.asyncio
    async def test_start_all_starts_all_sources(self):
        cache = PriceCache()
        sim = MagicMock(spec=SimulatorSource)
        sim.start = AsyncMock()
        yf = MagicMock(spec=YFinanceSource)
        yf.start = AsyncMock()
        massive = MagicMock(spec=MassiveSource)
        massive.start = AsyncMock()

        router = MarketDataRouter(simulator=sim, massive=massive, yfinance=yf, cache=cache)
        await router.start_all()

        sim.start.assert_called_once()
        massive.start.assert_called_once()
        yf.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_all_skips_massive_when_none(self):
        cache = PriceCache()
        sim = MagicMock(spec=SimulatorSource)
        sim.start = AsyncMock()
        yf = MagicMock(spec=YFinanceSource)
        yf.start = AsyncMock()

        router = MarketDataRouter(simulator=sim, massive=None, yfinance=yf, cache=cache)
        await router.start_all()

        sim.start.assert_called_once()
        yf.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_all_stops_all_sources(self):
        cache = PriceCache()
        sim = MagicMock(spec=SimulatorSource)
        sim.stop = AsyncMock()
        yf = MagicMock(spec=YFinanceSource)
        yf.stop = AsyncMock()
        massive = MagicMock(spec=MassiveSource)
        massive.stop = AsyncMock()

        router = MarketDataRouter(simulator=sim, massive=massive, yfinance=yf, cache=cache)
        await router.stop_all()

        sim.stop.assert_called_once()
        massive.stop.assert_called_once()
        yf.stop.assert_called_once()


class TestBuildRouter:
    def test_build_router_no_massive_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MASSIVE_API_KEY", None)
            router = build_router()
        assert router._massive is None
        assert isinstance(router._simulator, SimulatorSource)
        assert isinstance(router._yfinance, YFinanceSource)

    def test_build_router_with_massive_key(self):
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-api-key"}):
            router = build_router()
        assert router._massive is not None
        assert isinstance(router._massive, MassiveSource)

    def test_build_router_accepts_existing_cache(self):
        cache = PriceCache()
        router = build_router(cache=cache)
        assert router.cache is cache

    def test_resolve_indian_ticker_delegates_to_yfinance(self):
        cache = PriceCache()
        sim = MagicMock(spec=SimulatorSource)
        yf = MagicMock(spec=YFinanceSource)
        yf.resolve_ticker = MagicMock(return_value="RELIANCE.NS")

        router = MarketDataRouter(simulator=sim, massive=None, yfinance=yf, cache=cache)
        result = router.resolve_indian_ticker("RELIANCE")

        yf.resolve_ticker.assert_called_once_with("RELIANCE")
        assert result == "RELIANCE.NS"
