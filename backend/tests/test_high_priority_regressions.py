from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AnomalyScoreORM, AssetORM, MLPredictionORM
from app.db.session import Base
from app.repositories.ml import insert_prediction
from app.services.market_calendar import is_market_open


def test_market_calendar_handles_holidays_dst_and_exchanges():
    assert not is_market_open("AAPL", datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc))
    assert not is_market_open("PKN.WA", datetime(2026, 12, 25, 10, 0, tzinfo=timezone.utc))
    assert is_market_open("AAPL", datetime(2026, 7, 6, 15, 0, tzinfo=timezone.utc))
    assert is_market_open("PKN.WA", datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc))


def test_prediction_insert_is_an_upsert(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'upsert.db'}")
    Base.metadata.create_all(engine)
    snapshot = datetime(2026, 1, 2, tzinfo=timezone.utc)
    common = {
        "asset_id": "test",
        "snapshot_at": snapshot,
        "model_run_id": 1,
        "target_name": "target_up_5d",
        "predicted_label": "up",
        "raw_json": "{}",
    }
    with Session(engine) as db:
        insert_prediction(db, probability_up=0.6, **common)
        insert_prediction(db, probability_up=0.8, **common)
        db.commit()
        assert db.scalar(select(func.count()).select_from(MLPredictionORM)) == 1
        assert db.scalar(select(MLPredictionORM)).probability_up == 0.8


def test_anomaly_persist_populates_required_raw_response(tmp_path):
    from app.services.anomaly_service import _persist

    engine = create_engine(f"sqlite:///{tmp_path / 'anomaly.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.commit()
        _persist(
            db, "abc", datetime(2026, 1, 2, tzinfo=timezone.utc),
            42.0, False, 100, [{"feature": "rsi_14", "z_score": 1.2}], -0.12,
        )
        row = db.scalar(select(AnomalyScoreORM))
        assert row is not None
        assert '"decision_value": -0.12' in row.raw_response
