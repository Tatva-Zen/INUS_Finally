"""Tests for PriceTick, PriceCache."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.market.interface import PriceCache, PriceTick


def _make_tick(
    ticker: str = "AAPL",
    market: str = "us",
    price: float = 100.0,
    previous_price: float = 99.0,
    currency: str = "USD",
    stale: bool = False,
    source: str = "simulator",
) -> PriceTick:
    return PriceTick(
        ticker=ticker,
        market=market,  # type: ignore[arg-type]
        price=price,
        previous_price=previous_price,
        currency=currency,  # type: ignore[arg-type]
        timestamp=datetime.now(tz=timezone.utc),
        stale=stale,
        source=source,
    )


class TestPriceTick:
    def test_change_direction_up(self):
        tick = _make_tick(price=101.0, previous_price=100.0)
        assert tick.change_direction == "up"

    def test_change_direction_down(self):
        tick = _make_tick(price=99.0, previous_price=100.0)
        assert tick.change_direction == "down"

    def test_change_direction_flat(self):
        tick = _make_tick(price=100.0, previous_price=100.0)
        assert tick.change_direction == "flat"

    def test_default_stale_false(self):
        tick = _make_tick()
        assert tick.stale is False

    def test_stale_flag(self):
        tick = _make_tick(stale=True)
        assert tick.stale is True


class TestPriceCache:
    def test_get_missing_returns_none(self):
        cache = PriceCache()
        assert cache.get("UNKNOWN") is None

    def test_update_and_get(self):
        cache = PriceCache()
        tick = _make_tick(ticker="AAPL", price=190.0, previous_price=189.0)
        cache.update(tick)
        result = cache.get("AAPL")
        assert result is not None
        assert result.price == 190.0
        assert result.previous_price == 189.0

    def test_update_same_price_preserves_previous(self):
        """When price doesn't change, previous_price must remain the price before the last real move."""
        cache = PriceCache()

        # First tick: price moved from 189 → 190
        tick1 = _make_tick(ticker="AAPL", price=190.0, previous_price=189.0)
        cache.update(tick1)

        # Second tick: same price — previous_price should stay 189, not become 190
        tick2 = _make_tick(ticker="AAPL", price=190.0, previous_price=190.0)
        cache.update(tick2)

        result = cache.get("AAPL")
        assert result is not None
        assert result.price == 190.0
        assert result.previous_price == 189.0

    def test_update_new_price_updates_previous(self):
        cache = PriceCache()
        cache.update(_make_tick(ticker="AAPL", price=190.0, previous_price=189.0))
        cache.update(_make_tick(ticker="AAPL", price=191.0, previous_price=190.0))
        result = cache.get("AAPL")
        assert result is not None
        assert result.price == 191.0
        assert result.previous_price == 190.0

    def test_get_all_returns_all_tickers(self):
        cache = PriceCache()
        cache.update(_make_tick(ticker="AAPL", price=190.0, previous_price=189.0))
        cache.update(_make_tick(ticker="MSFT", price=420.0, previous_price=419.0))
        all_ticks = cache.get_all()
        tickers = {t.ticker for t in all_ticks}
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert len(all_ticks) == 2

    def test_mark_stale(self):
        cache = PriceCache()
        cache.update(_make_tick(ticker="AAPL", price=190.0, previous_price=189.0))
        cache.mark_stale("AAPL")
        result = cache.get("AAPL")
        assert result is not None
        assert result.stale is True
        assert result.price == 190.0  # price preserved

    def test_mark_stale_missing_ticker_is_noop(self):
        cache = PriceCache()
        cache.mark_stale("NONEXISTENT")  # must not raise

    def test_len(self):
        cache = PriceCache()
        assert len(cache) == 0
        cache.update(_make_tick(ticker="AAPL", price=190.0, previous_price=189.0))
        assert len(cache) == 1

    def test_thread_safety(self):
        """Concurrent updates from multiple threads must not corrupt the cache."""
        import threading

        cache = PriceCache()
        errors: list[Exception] = []

        def writer(ticker: str, count: int):
            try:
                for i in range(count):
                    cache.update(_make_tick(ticker=ticker, price=float(100 + i), previous_price=float(99 + i)))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(f"T{i}", 200)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(cache) == 10
