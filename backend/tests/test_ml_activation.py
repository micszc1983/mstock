from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    AssetORM, MLModelMonitorORM, MLModelRunORM, MLPredictionORM, MLTrainingRowORM,
)
from app.db.session import Base


def _safe_metrics() -> dict:
    return {
        "holdout_trades": 30,
        "holdout_avg_net_return_pct": 0.5,
        "holdout_profit_factor": 1.5,
        "cv_folds": 5,
        "deflated_sharpe_ratio": 0.8,
        "cpcv_paths": 5,
        "pbo": 0.1,
    }


def _run(now: datetime) -> MLModelRunORM:
    return MLModelRunORM(
        model_name="logistic_regression", target_name="target_up_5d",
        asset_id="abc", trained_at=now - timedelta(days=2), dataset_rows=200,
        metrics_json=json.dumps(_safe_metrics()), model_path="/model.joblib",
        is_active=True, deployment_role="champion",
    )


def test_activation_requires_fresh_live_evidence_and_honors_kill_switch(tmp_path):
    from app.services.ml_activation import activation_decision, set_emergency_disabled

    engine = create_engine(f"sqlite:///{tmp_path / 'activation.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        run = _run(now)
        db.add(run); db.flush()
        monitor = MLModelMonitorORM(
            model_run_id=run.id, checked_at=now, asset_id="abc",
            sample_size=19, is_degraded=False, action="keep",
            feature_psi=0.1, calibration_error=0.1,
            recent_avg_net_return_pct=0.4, recent_profit_factor=1.4,
            details_json="{}",
        )
        db.add(monitor); db.commit()

        shadow = activation_decision(db, run, monitor)
        assert shadow.eligible is False
        assert shadow.state == "shadow"
        assert "19/20" in shadow.reason

        monitor.sample_size = 20
        db.commit()
        live = activation_decision(db, run, monitor)
        assert live.eligible is True
        assert live.state == "eligible"

        set_emergency_disabled(db, True)
        blocked = activation_decision(db, run, monitor)
        assert blocked.eligible is False
        assert blocked.state == "disabled"


def test_prediction_monitor_uses_only_post_deployment_labeled_snapshots(tmp_path):
    from app.services.ml_monitoring import _prediction_outcome_metrics

    engine = create_engine(f"sqlite:///{tmp_path / 'outcomes.db'}")
    Base.metadata.create_all(engine)
    trained_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    snapshot = trained_at + timedelta(days=1)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        run = _run(trained_at + timedelta(days=2))
        run.trained_at = trained_at
        db.add(run); db.flush()
        db.add(MLTrainingRowORM(
            asset_id="abc", snapshot_at=snapshot, feature_json="{}",
            target_up_5d=1, target_return_5d=2.0,
        ))
        db.add(MLPredictionORM(
            asset_id="abc", snapshot_at=snapshot, model_run_id=run.id,
            target_name="target_up_5d", probability_up=0.7,
            predicted_label="up", raw_json="{}",
        ))
        db.commit()

        result = _prediction_outcome_metrics(run, db)
        assert result["sample_size"] == 1
        assert result["recent_avg_net_return_pct"] == 1.8
        assert result["coverage_pct"] == 100.0


def test_training_safety_rejects_negative_net_edge():
    from app.services.ml_activation import training_metrics_are_safe

    metrics = _safe_metrics()
    assert training_metrics_are_safe(metrics) is True
    metrics["holdout_avg_net_return_pct"] = -0.01
    assert training_metrics_are_safe(metrics) is False
