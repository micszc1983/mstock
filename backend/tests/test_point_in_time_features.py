from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    AssetORM, EarningsORM, InsiderTradeORM, NewsItemORM, NewsNLPRunORM, ShortInterestORM,
)
from app.db.session import Base


def test_event_news_taxonomy_handles_english_and_polish():
    from app.services.point_in_time_features import classify_news_events

    assert "earnings_guidance" in classify_news_events("Company raises earnings guidance")
    assert "contract_product" in classify_news_events("Spółka podpisała duży kontrakt")
    assert "legal_regulatory" in classify_news_events("Regulator wszczął śledztwo")


def test_point_in_time_features_respect_publication_boundaries(tmp_path):
    from app.services.point_in_time_features import PointInTimeFeatureStore

    engine = create_engine(f"sqlite:///{tmp_path / 'pit.db'}")
    Base.metadata.create_all(engine)
    utc = timezone.utc
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.add(EarningsORM(
            asset_id="abc", report_date=date(2025, 1, 10), eps_estimate=1.0,
            eps_actual=1.2, eps_surprise_pct=20.0, revenue_estimate=100.0,
            revenue_actual=110.0, is_upcoming=False,
            created_at=datetime(2025, 1, 10, 20, tzinfo=utc),
        ))
        db.add(InsiderTradeORM(
            asset_id="abc", transaction_date=date(2025, 1, 2),
            filing_date=date(2025, 1, 12), name="Director", transaction_code="P",
            transaction_type="buy", value=50_000.0, shares=500.0, price=100.0,
            created_at=datetime(2025, 1, 12, 18, tzinfo=utc),
        ))
        db.add(ShortInterestORM(
            asset_id="abc", report_date=date(2025, 1, 10), short_percent_float=0.08,
            short_ratio=2.5, created_at=datetime(2025, 1, 13, 18, tzinfo=utc),
        ))
        db.add_all([
            NewsItemORM(
                id="known", asset_id="abc", published_at=datetime(2025, 1, 14, 9, tzinfo=utc),
                source="wire", title="Company raises earnings guidance", body="",
                sentiment_score=0.8, impact_score=0.9,
            ),
            NewsItemORM(
                id="future", asset_id="abc", published_at=datetime(2025, 1, 15, 9, tzinfo=utc),
                source="wire", title="Regulator starts investigation", body="",
                sentiment_score=-0.9, impact_score=0.9,
            ),
        ])
        db.add_all([
            NewsNLPRunORM(
                news_id="known", model_name="test-nlp", processed_at=datetime(2025, 1, 14, 10, tzinfo=utc),
                sentiment_score=0.8, sentiment_label="positive", sentiment_confidence=0.9,
                relevance_score=0.9, raw_output_json="{}",
            ),
            NewsNLPRunORM(
                news_id="future", model_name="test-nlp", processed_at=datetime(2025, 1, 15, 10, tzinfo=utc),
                sentiment_score=-0.9, sentiment_label="negative", sentiment_confidence=0.9,
                relevance_score=0.9, raw_output_json="{}",
            ),
        ])
        db.commit()

        store = PointInTimeFeatureStore(db, "abc")
        before_filing = store.build(datetime(2025, 1, 12, 23, tzinfo=utc), has_iv=False)
        assert before_filing["has_insider_90d"] == 0.0
        assert before_filing["has_short_interest"] == 0.0

        price_dates = [date(2025, 1, 11) + timedelta(days=index) for index in range(7)]
        values = store.build(
            datetime(2025, 1, 14, 12, tzinfo=utc), has_iv=False,
            price_dates=price_dates, closes=[100, 101, 102, 104, 105, 106, 108],
        )
        assert values["has_iv"] == 0.0
        assert values["has_earnings"] == 1.0
        assert values["eps_surprise_pct"] == 20.0
        assert values["revenue_surprise_pct"] == 10.0
        assert values["has_insider_90d"] == 1.0
        assert values["insider_buy_ratio_90d"] == 1.0
        assert values["has_short_interest"] == 1.0
        assert values["news_count_7d"] == 1.0
        assert values["news_event_positive_7d"] > 0
        assert values["news_event_negative_7d"] == 0.0


def test_historical_news_count_uses_snapshot_not_wall_clock():
    from app.services.feature_builder import _news_count_7d

    class Item:
        def __init__(self, published_at):
            self.published_at = published_at

    anchor = datetime(2025, 2, 10, 12, tzinfo=timezone.utc)
    news = [
        Item(anchor - timedelta(days=2)),
        Item(anchor - timedelta(days=10)),
        Item(anchor + timedelta(hours=1)),
    ]
    assert _news_count_7d(news, anchor) == 1


def test_enriched_groups_require_saved_ablation_approval(tmp_path):
    from app.repositories.ml import upsert_setting
    from app.services.feature_ablation import approved_feature_names_for_training

    engine = create_engine(f"sqlite:///{tmp_path / 'approval.db'}")
    Base.metadata.create_all(engine)
    names = ["trend_score", "has_iv", "has_earnings", "news_event_positive_7d"]
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.commit()
        assert approved_feature_names_for_training(
            db, names, target_name="target_up_5d", asset_id="abc", market=None,
        ) == ["trend_score"]

        upsert_setting(
            db, "ml_feature_groups:target_up_5d:market:USA", '["earnings"]',
        )
        db.commit()
        assert approved_feature_names_for_training(
            db, names, target_name="target_up_5d", asset_id="abc", market=None,
        ) == ["trend_score", "has_earnings"]
