"""Tests for YFinanceSource (Indian market tickers)."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.market.interface import PriceCache, PriceTick
from app.market.yfinance_source import YFinanceSource


def _seed_tick(cache: PriceCache, ticker: str, price: float = 1000.0) -> None:
    cache.update(PriceTick(
        ticker=ticker,
        market="in",
        price=price,
        previous_price=price - 10.0,
        currency="INR",
        timestamp=datetime.now(tz=timezone.utc),
        source="yfinance",
    ))


class TestYFinanceAddRemove:
    def test_add_ns_ticker(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.NS")
        assert "RELIANCE.NS" in source.all_tickers()

    def test_add_bo_ticker(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.BO")
        assert "RELIANCE.BO" in source.all_tickers()

    def test_add_ticker_uppercased(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("reliance.ns")
        assert "RELIANCE.NS" in source.all_tickers()

    def test_add_us_ticker_raises(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        with pytest.raises(ValueError, match="YFinanceSource"):
            source.add_ticker("AAPL")

    def test_add_idempotent(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.NS")
        source.add_ticker("RELIANCE.NS")
        assert source.all_tickers().count("RELIANCE.NS") == 1

    def test_remove_ticker(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.NS")
        source.remove_ticker("RELIANCE.NS")
        assert "RELIANCE.NS" not in source.all_tickers()

    def test_remove_nonexistent_noop(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.remove_ticker("NONEXISTENT.NS")  # must not raise

    def test_all_tickers_empty_initially(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        assert source.all_tickers() == []


class TestYFinanceFetchAndUpdate:
    def test_fetch_single_updates_cache(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.NS")

        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = lambda self, key: MagicMock(iloc=MagicMock(__getitem__=lambda s, i: 2500.0))

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            source._fetch_and_update(["RELIANCE.NS"])

        tick = cache.get("RELIANCE.NS")
        assert tick is not None
        assert tick.market == "in"
        assert tick.currency == "INR"
        assert tick.source == "yfinance"

    def test_fetch_marks_stale_on_error(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.NS")
        _seed_tick(cache, "RELIANCE.NS", price=2500.0)

        mock_yf = MagicMock()
        mock_yf.download.side_effect = Exception("Yahoo Finance error")

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            source._fetch_and_update(["RELIANCE.NS"])

        tick = cache.get("RELIANCE.NS")
        assert tick is not None
        assert tick.stale is True
        assert tick.price == 2500.0  # last-known price preserved

    def test_nan_price_marks_stale(self):
        """When yfinance returns NaN for a ticker, it should be marked stale."""
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        source.add_ticker("RELIANCE.NS")
        _seed_tick(cache, "RELIANCE.NS", price=2500.0)

        mock_yf = MagicMock()

        import pandas as pd
        import numpy as np

        data = pd.DataFrame(
            {"RELIANCE.NS": [math.nan]},
        )
        # mock what _fetch_batch returns (nan)
        with patch.object(source, "_fetch_batch", return_value={"RELIANCE.NS": math.nan}):
            with patch.dict("sys.modules", {"yfinance": mock_yf}):
                source._fetch_and_update(["RELIANCE.NS"])

        tick = cache.get("RELIANCE.NS")
        assert tick is not None
        assert tick.stale is True


class TestYFinanceResolve:
    def test_resolve_ns_preferred(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.info = {"quoteType": "EQUITY"}

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = source.resolve_ticker("RELIANCE")

        assert result == "RELIANCE.NS"

    def test_resolve_falls_back_to_bo(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)

        call_count = [0]

        def mock_ticker(sym):
            t = MagicMock()
            if sym.endswith(".NS"):
                t.info = {"quoteType": None}
            else:
                t.info = {"quoteType": "EQUITY"}
            call_count[0] += 1
            return t

        mock_yf = MagicMock()
        mock_yf.Ticker.side_effect = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = source.resolve_ticker("RELIANCE")

        assert result == "RELIANCE.BO"

    def test_resolve_returns_none_for_unknown(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.info = {"quoteType": None}

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = source.resolve_ticker("FAKESTOCKXYZ")

        assert result is None

    def test_resolve_caches_result(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)

        call_count = [0]

        def mock_ticker(sym):
            t = MagicMock()
            t.info = {"quoteType": "EQUITY"}
            call_count[0] += 1
            return t

        mock_yf = MagicMock()
        mock_yf.Ticker.side_effect = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            first = source.resolve_ticker("RELIANCE")
            second = source.resolve_ticker("RELIANCE")

        assert first == second == "RELIANCE.NS"
        # Should only probe once (cached after first call)
        assert call_count[0] == 1

    def test_resolve_exception_returns_none(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)

        mock_yf = MagicMock()
        mock_yf.Ticker.side_effect = Exception("Network error")

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = source.resolve_ticker("RELIANCE")

        assert result is None

    def test_resolve_uppercase_normalization(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.info = {"quoteType": "EQUITY"}

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = source.resolve_ticker("reliance")

        assert result == "RELIANCE.NS"


class TestYFinanceLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache, poll_interval=60.0)
        await source.start()
        assert source._task is not None
        assert not source._task.done()
        await source.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache, poll_interval=60.0)
        await source.start()
        await source.stop()
        assert source._task is not None
        assert source._task.done()

    def test_get_price_delegates_to_cache(self):
        cache = PriceCache()
        source = YFinanceSource(cache=cache)
        assert source.get_price("RELIANCE.NS") is None
        _seed_tick(cache, "RELIANCE.NS")
        assert source.get_price("RELIANCE.NS") is not None
