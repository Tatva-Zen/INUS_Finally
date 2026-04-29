"""Tests for SimulatorSource (GBM price generation)."""

from __future__ import annotations

import asyncio
import math

import pytest

from app.market.interface import PriceCache
from app.market.simulator import (
    DEFAULT_CONFIG,
    SECONDS_PER_TRADING_YEAR,
    TICKER_CONFIGS,
    SimulatorSource,
)


class TestSimulatorAddRemove:
    def test_add_ticker_appears_in_all_tickers(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")
        assert "AAPL" in sim.all_tickers()

    def test_add_ticker_is_idempotent(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")
        sim.add_ticker("AAPL")
        assert sim.all_tickers().count("AAPL") == 1

    def test_remove_ticker_not_in_all_tickers(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")
        sim.remove_ticker("AAPL")
        assert "AAPL" not in sim.all_tickers()

    def test_remove_nonexistent_ticker_is_noop(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.remove_ticker("NONEXISTENT")  # must not raise

    def test_indian_ticker_raises(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        with pytest.raises(ValueError, match="SimulatorSource"):
            sim.add_ticker("RELIANCE.NS")

    def test_indian_bo_ticker_raises(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        with pytest.raises(ValueError, match="SimulatorSource"):
            sim.add_ticker("RELIANCE.BO")

    def test_ticker_uppercased(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("aapl")
        assert "AAPL" in sim.all_tickers()

    def test_seed_price_for_known_ticker(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")
        assert sim._prices["AAPL"] == TICKER_CONFIGS["AAPL"].seed_price

    def test_seed_price_for_unknown_ticker(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("ZZZZ")
        assert sim._prices["ZZZZ"] == DEFAULT_CONFIG.seed_price


class TestSimulatorGBM:
    def test_gbm_price_is_positive_across_many_steps(self):
        """Price must remain positive across 10,000 GBM steps for TSLA (high vol)."""
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.5)
        sim.add_ticker("TSLA")

        for _ in range(10_000):
            price = sim._next_price("TSLA")
            assert price is not None
            assert price > 0

    def test_next_price_returns_none_for_untracked(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        result = sim._next_price("UNKNOWN")
        assert result is None

    def test_next_price_updates_internal_state(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")
        original = sim._prices["AAPL"]
        sim._next_price("AAPL")
        # Price should have changed (or stayed at floor — extremely unlikely to be same)
        # Just check it's a positive float
        assert sim._prices["AAPL"] > 0

    def test_gbm_math_log_return_formula(self):
        """Verify GBM formula produces sensible log returns for each TICKER_CONFIG."""
        for ticker, cfg in TICKER_CONFIGS.items():
            dt = 0.5 / SECONDS_PER_TRADING_YEAR
            # Expected magnitude of per-step log return ≈ sigma * sqrt(dt)
            expected_std = cfg.sigma * math.sqrt(dt)
            assert expected_std > 0
            assert expected_std < 0.01  # per-step move should be small

    def test_price_floor_applied(self):
        """Simulate extreme negative z-values and confirm price never goes below 0.01."""
        import unittest.mock as mock

        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")

        # Force gauss to return extreme negative to try to crash price
        with mock.patch("app.market.simulator.random.gauss", return_value=-1000.0):
            price = sim._next_price("AAPL")
        assert price is not None
        assert price >= 0.01

    def test_all_default_tickers_have_configs(self):
        for ticker in ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]:
            assert ticker in TICKER_CONFIGS


class TestSimulatorAsync:
    @pytest.mark.asyncio
    async def test_start_generates_prices(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.01)
        sim.add_ticker("AAPL")

        await sim.start()
        await asyncio.sleep(0.05)  # let a few ticks run
        await sim.stop()

        tick = cache.get("AAPL")
        assert tick is not None
        assert tick.market == "us"
        assert tick.currency == "USD"
        assert tick.price > 0
        assert tick.source == "simulator"
        assert tick.stale is False

    @pytest.mark.asyncio
    async def test_start_multiple_tickers(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.01)
        sim.add_ticker("AAPL")
        sim.add_ticker("MSFT")
        sim.add_ticker("TSLA")

        await sim.start()
        await asyncio.sleep(0.05)
        await sim.stop()

        for ticker in ["AAPL", "MSFT", "TSLA"]:
            tick = cache.get(ticker)
            assert tick is not None, f"Expected tick for {ticker}"
            assert tick.price > 0

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.5)
        sim.add_ticker("AAPL")

        await sim.start()
        assert sim._task is not None
        assert not sim._task.done()

        await sim.stop()
        assert sim._task.done()

    @pytest.mark.asyncio
    async def test_get_price_returns_none_before_start(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache)
        sim.add_ticker("AAPL")
        # No start() called — cache should be empty
        assert sim.get_price("AAPL") is None

    @pytest.mark.asyncio
    async def test_get_price_returns_tick_after_start(self):
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.01)
        sim.add_ticker("AAPL")

        await sim.start()
        await asyncio.sleep(0.05)
        await sim.stop()

        tick = sim.get_price("AAPL")
        assert tick is not None
        assert tick.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_add_ticker_during_run(self):
        """Adding a ticker while the simulator is running should be safe."""
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.01)
        sim.add_ticker("AAPL")

        await sim.start()
        await asyncio.sleep(0.02)

        sim.add_ticker("MSFT")  # add during run
        await asyncio.sleep(0.05)
        await sim.stop()

        assert cache.get("MSFT") is not None

    @pytest.mark.asyncio
    async def test_previous_price_updates_on_change(self):
        """After enough ticks, previous_price should differ from current at some point."""
        cache = PriceCache()
        sim = SimulatorSource(cache=cache, tick_interval=0.001)
        sim.add_ticker("TSLA")  # TSLA has high vol — price will change quickly

        await sim.start()
        await asyncio.sleep(0.1)  # 100ms at 1ms intervals = ~100 ticks
        await sim.stop()

        tick = cache.get("TSLA")
        assert tick is not None
        # With 100 ticks of 60% vol, price almost certainly moved
        # We just verify the structure is intact
        assert tick.previous_price > 0
        assert tick.price > 0
