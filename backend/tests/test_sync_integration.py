from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import AssetORM, NewsItemORM, PricePointORM, SyncLogORM
from app.db.session import Base
from app.repositories.sync_logs import add_sync_log
from app.schemas.asset import PricePoint
from app.schemas.common import AssetType, NarrativeLabel
from app.schemas.news import NewsItem
from app.services.sync import log_sync_success, sync_news_for_asset, sync_prices_for_asset


def build_test_session(tmp_path):
    db_file = tmp_path / "sync_integration.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def seed_asset(db, asset_id: str, symbol: str, name: str, asset_type: str):
    db.add(
        AssetORM(
            id=asset_id,
            symbol=symbol,
            name=name,
            type=asset_type,
            sector=None,
            description=None,
        )
    )
    db.commit()


def test_sync_prices_service_persists_rows(tmp_path, monkeypatch):
    TestingSessionLocal = build_test_session(tmp_path)

    from app.services import sync as sync_service

    with TestingSessionLocal() as db:
        seed_asset(db, "nvda", "NVDA", "NVIDIA", "stock")

        def fake_fetch_stock_prices(symbol: str):
            assert symbol == "NVDA"
            return [
                PricePoint(
                    timestamp=datetime(2026, 4, 10, tzinfo=timezone.utc),
                    open=100.0,
                    high=105.0,
                    low=99.0,
                    close=103.0,
                    volume=12345.0,
                ),
                PricePoint(
                    timestamp=datetime(2026, 4, 11, tzinfo=timezone.utc),
                    open=103.0,
                    high=106.0,
                    low=101.0,
                    close=104.0,
                    volume=23456.0,
                ),
            ]

        monkeypatch.setattr(sync_service, "fetch_stock_prices_from_alpha_vantage", fake_fetch_stock_prices)

        asset = db.get(AssetORM, "nvda")
        result = sync_prices_for_asset(db, asset)

        assert result.inserted == 2
        assert result.skipped == 0

        rows = db.scalars(
            select(PricePointORM).where(PricePointORM.asset_id == "nvda").order_by(PricePointORM.timestamp.asc())
        ).all()
        assert len(rows) == 2
        assert rows[-1].close == 104.0


def test_sync_news_service_persists_rows_and_narratives(tmp_path, monkeypatch):
    TestingSessionLocal = build_test_session(tmp_path)

    from app.services import sync as sync_service

    with TestingSessionLocal() as db:
        seed_asset(db, "nvda", "NVDA", "NVIDIA", "stock")

        def fake_fetch_company_news(symbol: str, asset_id: str, asset_type: AssetType):
            assert symbol == "NVDA"
            assert asset_id == "nvda"
            assert asset_type == AssetType.STOCK
            return [
                NewsItem(
                    id="mock-news-1",
                    asset_id="nvda",
                    published_at=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
                    source="MockSource",
                    title="AI demand remains strong",
                    body="GPU orders and AI capex remain strong",
                    sentiment_score=0.65,
                    impact_score=0.8,
                    narratives={
                        NarrativeLabel.AI_GROWTH: 0.9,
                        NarrativeLabel.DEMAND_STRENGTH: 0.7,
                    },
                )
            ]

        monkeypatch.setattr(sync_service, "fetch_company_news_from_finnhub", fake_fetch_company_news)

        asset = db.get(AssetORM, "nvda")
        result = sync_news_for_asset(db, asset)

        assert result.inserted == 1
        assert result.skipped == 0

        rows = db.scalars(select(NewsItemORM).where(NewsItemORM.asset_id == "nvda")).all()
        assert len(rows) == 1
        assert rows[0].source == "MockSource"
        assert len(rows[0].narratives) == 2
        assert {n.narrative_label for n in rows[0].narratives} == {"ai_growth", "demand_strength"}


def test_sync_prices_second_run_updates_without_duplicate_insert(tmp_path, monkeypatch):
    TestingSessionLocal = build_test_session(tmp_path)

    from app.services import sync as sync_service

    with TestingSessionLocal() as db:
        seed_asset(db, "nvda", "NVDA", "NVIDIA", "stock")

        def fake_fetch_stock_prices_v1(symbol: str):
            return [
                PricePoint(
                    timestamp=datetime(2026, 4, 10, tzinfo=timezone.utc),
                    open=100.0,
                    high=105.0,
                    low=99.0,
                    close=103.0,
                    volume=12345.0,
                )
            ]

        monkeypatch.setattr(sync_service, "fetch_stock_prices_from_alpha_vantage", fake_fetch_stock_prices_v1)
        asset = db.get(AssetORM, "nvda")
        first = sync_prices_for_asset(db, asset)
        assert first.inserted == 1

        def fake_fetch_stock_prices_v2(symbol: str):
            return [
                PricePoint(
                    timestamp=datetime(2026, 4, 10, tzinfo=timezone.utc),
                    open=100.0,
                    high=106.0,
                    low=98.0,
                    close=104.5,
                    volume=55555.0,
                )
            ]

        monkeypatch.setattr(sync_service, "fetch_stock_prices_from_alpha_vantage", fake_fetch_stock_prices_v2)
        second = sync_prices_for_asset(db, asset)
        assert second.inserted == 0
        assert second.skipped == 1

        rows = db.scalars(select(PricePointORM).where(PricePointORM.asset_id == "nvda")).all()
        assert len(rows) == 1
        assert rows[0].close == 104.5
        assert rows[0].volume == 55555.0


def test_sync_news_second_run_updates_existing_item(tmp_path, monkeypatch):
    TestingSessionLocal = build_test_session(tmp_path)

    from app.services import sync as sync_service

    with TestingSessionLocal() as db:
        seed_asset(db, "gold", "XAU", "Gold", "metal")

        def fake_search_news_v1(term: str, asset_id: str, asset_type: AssetType):
            return [
                NewsItem(
                    id="mock-gold-1",
                    asset_id="gold",
                    published_at=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
                    source="AlphaMock",
                    title="Gold supported by safe haven demand",
                    body="Geopolitical stress boosts demand",
                    sentiment_score=0.4,
                    impact_score=0.7,
                    narratives={NarrativeLabel.SAFE_HAVEN: 0.9},
                )
            ]

        monkeypatch.setattr(sync_service, "fetch_search_news_from_alpha_vantage", fake_search_news_v1)
        asset = db.get(AssetORM, "gold")
        first = sync_news_for_asset(db, asset)
        assert first.inserted == 1

        def fake_search_news_v2(term: str, asset_id: str, asset_type: AssetType):
            return [
                NewsItem(
                    id="mock-gold-1",
                    asset_id="gold",
                    published_at=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
                    source="AlphaMock",
                    title="Gold supported by central bank buying",
                    body="Reserve diversification also supports prices",
                    sentiment_score=0.55,
                    impact_score=0.85,
                    narratives={
                        NarrativeLabel.SAFE_HAVEN: 0.5,
                        NarrativeLabel.CENTRAL_BANK_BUYING: 0.8,
                    },
                )
            ]

        monkeypatch.setattr(sync_service, "fetch_search_news_from_alpha_vantage", fake_search_news_v2)
        second = sync_news_for_asset(db, asset)
        assert second.inserted == 0
        assert second.skipped == 1

        rows = db.scalars(select(NewsItemORM).where(NewsItemORM.asset_id == "gold")).all()
        assert len(rows) == 1
        assert rows[0].title == "Gold supported by central bank buying"
        assert len(rows[0].narratives) == 2


def test_log_sync_success_persists_sync_log(tmp_path, monkeypatch):
    TestingSessionLocal = build_test_session(tmp_path)

    from app.services import sync as sync_service

    with TestingSessionLocal() as db:
        seed_asset(db, "nvda", "NVDA", "NVIDIA", "stock")

        def fake_fetch_stock_prices(symbol: str):
            return [
                PricePoint(
                    timestamp=datetime(2026, 4, 10, tzinfo=timezone.utc),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000.0,
                )
            ]

        monkeypatch.setattr(sync_service, "fetch_stock_prices_from_alpha_vantage", fake_fetch_stock_prices)

        asset = db.get(AssetORM, "nvda")
        result = sync_prices_for_asset(db, asset)
        log_sync_success(db, "nvda", "prices", result)

        logs = db.scalars(select(SyncLogORM).where(SyncLogORM.asset_id == "nvda")).all()
        assert len(logs) == 1
        assert logs[0].sync_type == "prices"
        assert logs[0].status == "success"
        assert logs[0].inserted == 1
