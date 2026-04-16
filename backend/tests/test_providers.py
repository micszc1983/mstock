from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.schemas.common import AssetType
from app.services import providers


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class DummyClient:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        return DummyResponse(self.payload)


def test_fetch_stock_prices_from_alpha_vantage(monkeypatch):
    payload = {
        "Time Series (Daily)": {
            "2026-04-10": {
                "1. open": "100.0",
                "2. high": "105.0",
                "3. low": "99.0",
                "4. close": "103.0",
                "5. volume": "12345",
            },
            "2026-04-11": {
                "1. open": "103.0",
                "2. high": "106.0",
                "3. low": "101.0",
                "4. close": "104.0",
                "5. volume": "23456",
            },
        }
    }

    monkeypatch.setattr(providers.settings, "alphavantage_api_key", "test-key")
    monkeypatch.setattr(providers.httpx, "Client", lambda timeout: DummyClient(payload))

    rows = providers.fetch_stock_prices_from_alpha_vantage("NVDA")
    assert len(rows) == 2
    assert rows[-1].close == 104.0


def test_fetch_metal_prices_from_alpha_vantage(monkeypatch):
    payload = {
        "data": [
            {"date": "2026-04-10", "value": "2200.5"},
            {"date": "2026-04-11", "value": "2210.0"},
        ]
    }

    monkeypatch.setattr(providers.settings, "alphavantage_api_key", "test-key")
    monkeypatch.setattr(providers.httpx, "Client", lambda timeout: DummyClient(payload))

    rows = providers.fetch_metal_prices_from_alpha_vantage("GOLD")
    assert len(rows) == 2
    assert rows[-1].close == 2210.0
    assert rows[-1].volume == 0.0


def test_fetch_company_news_from_finnhub(monkeypatch):
    payload = [
        {
            "id": 123,
            "datetime": 1775865600,
            "headline": "AI demand remains strong",
            "summary": "Strong GPU demand continues",
            "source": "MockSource",
        }
    ]

    monkeypatch.setattr(providers.settings, "finnhub_api_key", "test-key")
    monkeypatch.setattr(providers.httpx, "Client", lambda timeout: DummyClient(payload))

    items = providers.fetch_company_news_from_finnhub("NVDA", "nvda", AssetType.STOCK)
    assert len(items) == 1
    assert items[0].asset_id == "nvda"
    assert items[0].source == "MockSource"
    assert "ai_growth" in items[0].narratives


def test_fetch_search_news_from_alpha_vantage(monkeypatch):
    payload = {
        "feed": [
            {
                "title": "Gold supported by central bank buying",
                "summary": "Safe haven and reserve diversification support prices",
                "time_published": "20260411T120000",
                "source": "MockAlpha",
                "url": "https://example.com/gold-news",
                "overall_sentiment_score": "0.42",
            }
        ]
    }

    monkeypatch.setattr(providers.settings, "alphavantage_api_key", "test-key")
    monkeypatch.setattr(providers.httpx, "Client", lambda timeout: DummyClient(payload))

    items = providers.fetch_search_news_from_alpha_vantage("gold", "gold", AssetType.METAL)
    assert len(items) == 1
    assert items[0].sentiment_score == 0.42
    assert items[0].source == "MockAlpha"


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(providers.settings, "alphavantage_api_key", "")
    with pytest.raises(HTTPException):
        providers.fetch_stock_prices_from_alpha_vantage("NVDA")
