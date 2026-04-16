from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import AssetORM, NewsItemORM, NewsNarrativeORM, PricePointORM, SyncLogORM
from app.mappers import asset_to_schema, news_to_schema, price_to_schema, sync_log_to_schema


def test_asset_mapper():
    orm = AssetORM(id="nvda", symbol="NVDA", name="NVIDIA", type="stock", sector="Semis", description=None)
    schema = asset_to_schema(orm)
    assert schema.id == "nvda"
    assert schema.type == "stock"


def test_price_mapper():
    orm = PricePointORM(
        asset_id="nvda",
        timestamp=datetime.now(timezone.utc),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=1000,
    )
    schema = price_to_schema(orm)
    assert schema.close == 1.5


def test_news_mapper():
    orm = NewsItemORM(
        id="n1",
        asset_id="nvda",
        published_at=datetime.now(timezone.utc),
        source="X",
        title="Title",
        body="Body",
        sentiment_score=0.2,
        impact_score=0.8,
    )
    orm.narratives = [NewsNarrativeORM(narrative_label="ai_growth", score=0.9)]
    schema = news_to_schema(orm)
    assert schema.narratives["ai_growth"] == 0.9


def test_sync_log_mapper():
    orm = SyncLogORM(
        id=1,
        asset_id="nvda",
        sync_type="news",
        provider="test",
        inserted=2,
        skipped=1,
        status="success",
        detail="ok",
        created_at=datetime.now(timezone.utc),
    )
    schema = sync_log_to_schema(orm)
    assert schema.inserted == 2
