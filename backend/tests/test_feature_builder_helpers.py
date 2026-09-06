from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AssetORM, DailyAssetFeatureORM, ForecastORM, MLTrainingRowORM
from app.db.session import Base
from app.services.feature_builder import _range_rank, _remove_incomplete_daily_derivatives


def test_range_rank_is_bounded_for_value_above_history():
    assert _range_rank(30.0, [10.0, 20.0]) == 100.0


def test_range_rank_is_bounded_for_value_below_history():
    assert _range_rank(5.0, [10.0, 20.0]) == 0.0


def test_range_rank_handles_flat_history():
    assert _range_rank(10.0, [10.0, 10.0]) == 50.0


def _feature(asset_id: str, timestamp: datetime) -> DailyAssetFeatureORM:
    return DailyAssetFeatureORM(
        asset_id=asset_id, snapshot_at=timestamp, last_price=100.0,
        price_change_1d_pct=0.0, price_change_5d_pct=0.0, price_change_20d_pct=0.0,
        trend_score=50.0, sentiment_score=0.0, narrative_shift_score=0.0,
        divergence_score=0.0, fragility_score=0.0, regime_label="range_bound",
        regime_confidence=50.0, dominant_narrative=None, volatility_10d=1.0,
        momentum_20d=0.0, news_count_7d=0,
    )


def test_incomplete_daily_derivatives_are_removed_without_touching_closed_day(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'daily-cleanup.db'}")
    Base.metadata.create_all(engine)
    closed = datetime(2026, 8, 11, tzinfo=timezone.utc)
    incomplete = datetime(2026, 8, 12, tzinfo=timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(
            id="abc", symbol="ABC", name="ABC", type="stock",
            currency="USD", price_symbol="ABC",
        ))
        db.add_all([_feature("abc", closed), _feature("abc", incomplete)])
        db.add(ForecastORM(
            asset_id="abc", generated_at=incomplete, horizon="5d", direction="up",
            up_probability=0.6, down_probability=0.4, confidence=60.0,
            expected_return_pct=1.0, expected_range_low=99.0,
            expected_range_high=102.0, model_name="test", regime_label="range_bound",
        ))
        db.add(MLTrainingRowORM(
            asset_id="abc", snapshot_at=incomplete, feature_json="{}",
        ))
        db.commit()

        removed = _remove_incomplete_daily_derivatives(db, "abc", [incomplete])
        db.commit()

        remaining_days = db.scalars(select(DailyAssetFeatureORM.snapshot_at)).all()
        assert [value.date() for value in remaining_days] == [closed.date()]
        assert db.scalar(select(func.count()).select_from(ForecastORM)) == 0
        assert db.scalar(select(func.count()).select_from(MLTrainingRowORM)) == 0
        assert removed == 3
