"""Tests for MassiveSource (Massive/Polygon.io API client)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.interface import PriceCache, PriceTick
from app.market.massive import MassiveSource


def _make_snapshot(ticker: str, min_close: float | None = None, day_close: float | None = None, prev_close: float | None = None) -> dict:
    snap: dict = {"ticker": ticker}
    if min_close is not None:
        snap["min"] = {"c": min_close}
    if day_close is not None:
        snap["day"] = {"c": day_close}
    if prev_close is not None:
        snap["prevDay"] = {"c": prev_close}
    return snap


class TestMassiveAddRemove:
    def test_add_ticker(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        source.add_ticker("AAPL")
        assert "AAPL" in source.all_tickers()

    def test_add_ticker_uppercased(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        source.add_ticker("aapl")
        assert "AAPL" in source.all_tickers()

    def test_add_ticker_idempotent(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        source.add_ticker("AAPL")
        source.add_ticker("AAPL")
        assert source.all_tickers().count("AAPL") == 1

    def test_indian_ticker_raises(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        with pytest.raises(ValueError, match="MassiveSource"):
            source.add_ticker("RELIANCE.NS")

    def test_remove_ticker(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        source.add_ticker("AAPL")
        source.remove_ticker("AAPL")
        assert "AAPL" not in source.all_tickers()

    def test_remove_nonexistent_noop(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        source.remove_ticker("NONEXISTENT")  # must not raise

    def test_all_tickers_empty_initially(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        assert source.all_tickers() == []


class TestMassiveExtractPrice:
    def test_prefers_min_close(self):
        snap = _make_snapshot("AAPL", min_close=150.0, day_close=149.0, prev_close=148.0)
        price = MassiveSource._extract_price(snap)
        assert price == 150.0

    def test_falls_back_to_day_close(self):
        snap = _make_snapshot("AAPL", day_close=149.0, prev_close=148.0)
        price = MassiveSource._extract_price(snap)
        assert price == 149.0

    def test_falls_back_to_prev_day(self):
        snap = _make_snapshot("AAPL", prev_close=148.0)
        price = MassiveSource._extract_price(snap)
        assert price == 148.0

    def test_returns_none_when_no_price(self):
        snap: dict = {"ticker": "AAPL"}
        price = MassiveSource._extract_price(snap)
        assert price is None

    def test_returns_none_for_zero_min_close(self):
        snap = _make_snapshot("AAPL", min_close=0, day_close=149.0)
        # 0 is falsy — should fall through to day close
        price = MassiveSource._extract_price(snap)
        assert price == 149.0


class TestMassiveFetchAndUpdate:
    @pytest.mark.asyncio
    async def test_fetch_and_update_populates_cache(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache, poll_interval=60.0)
        source.add_ticker("AAPL")
        source.add_ticker("MSFT")

        response_data = {
            "tickers": [
                _make_snapshot("AAPL", min_close=190.0),
                _make_snapshot("MSFT", day_close=420.0),
            ]
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        source._client = mock_client

        await source._fetch_and_update(["AAPL", "MSFT"])

        aapl = cache.get("AAPL")
        assert aapl is not None
        assert aapl.price == 190.0
        assert aapl.market == "us"
        assert aapl.currency == "USD"
        assert aapl.source == "massive"
        assert aapl.stale is False

        msft = cache.get("MSFT")
        assert msft is not None
        assert msft.price == 420.0

    @pytest.mark.asyncio
    async def test_missing_ticker_in_response_marked_stale(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        source.add_ticker("AAPL")
        source.add_ticker("NFLX")

        # Seed NFLX so mark_stale has something to work with
        from datetime import datetime, timezone
        from app.market.interface import PriceTick
        cache.update(PriceTick(
            ticker="NFLX", market="us", price=680.0, previous_price=675.0,
            currency="USD", timestamp=datetime.now(tz=timezone.utc), source="massive"
        ))

        response_data = {"tickers": [_make_snapshot("AAPL", min_close=190.0)]}
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        source._client = mock_client

        await source._fetch_and_update(["AAPL", "NFLX"])

        nflx = cache.get("NFLX")
        assert nflx is not None
        assert nflx.stale is True

    @pytest.mark.asyncio
    async def test_http_error_marks_all_stale(self):
        """On HTTP failure the poll loop marks all tickers stale."""
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache, poll_interval=60.0)
        source.add_ticker("AAPL")

        # Seed cache
        from datetime import datetime, timezone
        from app.market.interface import PriceTick
        cache.update(PriceTick(
            ticker="AAPL", market="us", price=190.0, previous_price=189.0,
            currency="USD", timestamp=datetime.now(tz=timezone.utc), source="massive"
        ))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        source._client = mock_client

        # Simulate one iteration of poll loop
        with pytest.raises(Exception):
            await source._fetch_and_update(["AAPL"])

        # The poll loop itself catches errors and calls mark_stale
        source._cache.mark_stale("AAPL")
        tick = cache.get("AAPL")
        assert tick is not None
        assert tick.stale is True
        assert tick.price == 190.0  # last-known price preserved


class TestMassiveLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_client_and_task(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache, poll_interval=60.0)

        with patch("app.market.massive.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            await source.start()
            assert source._task is not None
            assert not source._task.done()
            await source.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache, poll_interval=60.0)

        with patch("app.market.massive.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            await source.start()
            await source.stop()

            assert source._task is not None
            assert source._task.done()

    def test_get_price_delegates_to_cache(self):
        cache = PriceCache()
        source = MassiveSource(api_key="test-key", cache=cache)
        assert source.get_price("AAPL") is None  # cache empty
