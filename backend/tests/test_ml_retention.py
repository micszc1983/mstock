from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AssetORM, MLModelRunORM, MLPredictionORM
from app.db.session import Base
from app.services.ml_retention import prune_model_runs


def _run(index: int, *, active: bool = False) -> MLModelRunORM:
    return MLModelRunORM(
        model_name="logistic_regression",
        target_name="target_up_5d",
        asset_id="abc",
        trained_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        dataset_rows=100,
        metrics_json="{}",
        model_path=f"/models/{index}.joblib",
        is_active=active,
        deployment_role="champion" if active else "archived",
    )


def test_model_run_retention_keeps_latest_active_and_referenced(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        runs = [_run(index, active=index == 0) for index in range(20)]
        db.add_all(runs)
        db.flush()
        db.add(MLPredictionORM(
            asset_id="abc",
            snapshot_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            model_run_id=runs[1].id,
            target_name="target_up_5d",
            probability_up=0.6,
            predicted_label="up",
            raw_json="{}",
        ))
        db.commit()

        preview = prune_model_runs(db, keep_per_group=15, dry_run=True)
        assert preview.total_before == 20
        assert preview.would_delete == 3
        assert preview.deleted == 0

        result = prune_model_runs(db, keep_per_group=15, dry_run=False)
        remaining = list(db.scalars(select(MLModelRunORM).order_by(MLModelRunORM.id)).all())
        assert result.deleted == 3
        assert len(remaining) == 17
        assert runs[0].id in {row.id for row in remaining}
        assert runs[1].id in {row.id for row in remaining}
        assert db.scalar(select(func.count()).select_from(MLPredictionORM)) == 1
