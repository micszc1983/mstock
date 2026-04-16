from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import NewsItemORM, PricePointORM, SyncLogORM
from app.schemas.asset import PricePoint
from app.schemas.common import AssetType, NarrativeLabel
from app.schemas.news import NewsItem


def test_sync_prices_endpoint_end_to_end(test_app, monkeypatch):
    from app.services import sync as sync_service

    def fake_fetch_stock_prices(symbol: str):
        assert symbol == "NVDA"
        return [
            PricePoint(
                timestamp=datetime(2026, 4, 12, tzinfo=timezone.utc),
                open=110.0,
                high=112.0,
                low=109.0,
                close=111.5,
                volume=20000.0,
            )
        ]

    monkeypatch.setattr(sync_service, "fetch_stock_prices_from_alpha_vantage", fake_fetch_stock_prices)

    response = test_app.post("/sync/prices/nvda")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "nvda"
    assert payload["inserted"] == 1

    # verify via API-visible state
    prices_response = test_app.get("/assets/nvda/prices?limit=5")
    assert prices_response.status_code == 200
    prices = prices_response.json()
    assert any(float(row["close"]) == 111.5 for row in prices)

    logs_response = test_app.get("/sync/logs")
    assert logs_response.status_code == 200
    logs = logs_response.json()
    assert any(log["asset_id"] == "nvda" and log["sync_type"] == "prices" and log["status"] == "success" for log in logs)


def test_sync_news_endpoint_end_to_end(test_app, monkeypatch):
    from app.services import sync as sync_service

    def fake_fetch_company_news(symbol: str, asset_id: str, asset_type: AssetType):
        assert symbol == "NVDA"
        assert asset_id == "nvda"
        assert asset_type == AssetType.STOCK
        return [
            NewsItem(
                id="api-mock-news-1",
                asset_id="nvda",
                published_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
                source="MockEndpointSource",
                title="AI demand accelerates again",
                body="GPU demand and AI infrastructure spending remain strong",
                sentiment_score=0.7,
                impact_score=0.9,
                narratives={
                    NarrativeLabel.AI_GROWTH: 0.95,
                    NarrativeLabel.DEMAND_STRENGTH: 0.75,
                },
            )
        ]

    monkeypatch.setattr(sync_service, "fetch_company_news_from_finnhub", fake_fetch_company_news)

    response = test_app.post("/sync/news/nvda")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "nvda"
    assert payload["inserted"] == 1

    news_response = test_app.get("/assets/nvda/news?limit=20")
    assert news_response.status_code == 200
    news_items = news_response.json()
    inserted = [item for item in news_items if item["id"] == "api-mock-news-1"]
    assert len(inserted) == 1
    assert inserted[0]["source"] == "MockEndpointSource"

    logs_response = test_app.get("/sync/logs")
    logs = logs_response.json()
    assert any(log["asset_id"] == "nvda" and log["sync_type"] == "news" and log["status"] == "success" for log in logs)


def test_sync_all_endpoint_end_to_end_with_mixed_assets(test_app, monkeypatch):
    from app.services import sync as sync_service

    def fake_fetch_stock_prices(symbol: str):
        return [
            PricePoint(
                timestamp=datetime(2026, 4, 13, tzinfo=timezone.utc),
                open=120.0,
                high=121.0,
                low=118.0,
                close=119.5,
                volume=15000.0,
            )
        ]

    def fake_fetch_metal_prices(function_name: str):
        return [
            PricePoint(
                timestamp=datetime(2026, 4, 13, tzinfo=timezone.utc),
                open=2300.0,
                high=2300.0,
                low=2300.0,
                close=2300.0,
                volume=0.0,
            )
        ]

    def fake_fetch_company_news(symbol: str, asset_id: str, asset_type: AssetType):
        return [
            NewsItem(
                id=f"sync-all-stock-news-{asset_id}",
                asset_id=asset_id,
                published_at=datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc),
                source="MockStockNews",
                title="Demand remains constructive",
                body="Growth outlook remains constructive",
                sentiment_score=0.45,
                impact_score=0.7,
                narratives={NarrativeLabel.DEMAND_STRENGTH: 0.8},
            )
        ]

    def fake_fetch_search_news(term: str, asset_id: str, asset_type: AssetType):
        return [
            NewsItem(
                id=f"sync-all-search-news-{asset_id}",
                asset_id=asset_id,
                published_at=datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc),
                source="MockSearchNews",
                title="Safe haven demand remains visible",
                body="Geopolitical concerns support flows",
                sentiment_score=0.35,
                impact_score=0.65,
                narratives={NarrativeLabel.SAFE_HAVEN: 0.85},
            )
        ]

    monkeypatch.setattr(sync_service, "fetch_stock_prices_from_alpha_vantage", fake_fetch_stock_prices)
    monkeypatch.setattr(sync_service, "fetch_metal_prices_from_alpha_vantage", fake_fetch_metal_prices)
    monkeypatch.setattr(sync_service, "fetch_company_news_from_finnhub", fake_fetch_company_news)
    monkeypatch.setattr(sync_service, "fetch_search_news_from_alpha_vantage", fake_fetch_search_news)

    response = test_app.post("/sync/all")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 2
    assert any(row["asset_id"] == "nvda" for row in rows)
    assert any(row["asset_id"] == "gold" for row in rows)

    logs_response = test_app.get("/sync/logs?limit=200")
    assert logs_response.status_code == 200
    logs = logs_response.json()
    assert any(log["asset_id"] == "nvda" and log["sync_type"] == "prices" for log in logs)
    assert any(log["asset_id"] == "gold" and log["sync_type"] == "news" for log in logs)


def test_sync_news_endpoint_logs_error_when_provider_fails(test_app, monkeypatch):
    from fastapi import HTTPException
    from app.services import sync as sync_service

    def failing_fetch_company_news(symbol: str, asset_id: str, asset_type: AssetType):
        raise HTTPException(status_code=502, detail="Mock provider failure")

    monkeypatch.setattr(sync_service, "fetch_company_news_from_finnhub", failing_fetch_company_news)

    response = test_app.post("/sync/news/nvda")
    assert response.status_code == 502
    assert response.json()["detail"] == "Mock provider failure"

    logs_response = test_app.get("/sync/logs")
    logs = logs_response.json()
    assert any(
        log["asset_id"] == "nvda"
        and log["sync_type"] == "news"
        and log["status"] == "error"
        and "Mock provider failure" in log["detail"]
        for log in logs
    )


def test_sync_prices_unknown_asset_returns_404(test_app):
    response = test_app.post("/sync/prices/unknown-asset")
    assert response.status_code == 404
