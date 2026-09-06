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

        monitor.details_json = json.dumps({"drift_confirmation_pending": True})
        db.commit()
        pending = activation_decision(db, run, monitor)
        assert pending.eligible is False
        assert pending.state == "shadow"
        assert "potwierdzenie driftu" in pending.reason

        monitor.details_json = json.dumps({"drift_ready": False})
        db.commit()
        no_drift_sample = activation_decision(db, run, monitor)
        assert no_drift_sample.eligible is False
        assert "aktualnych cech" in no_drift_sample.reason

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


def test_drift_uses_latest_market_rows_not_oldest_limited_slice(tmp_path, monkeypatch):
    from app.services.ml_monitoring import _population_stability_report

    engine = create_engine(f"sqlite:///{tmp_path / 'market-drift.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    metrics = {
        "feature_names": ["signal"],
        "feature_reference": {
            "signal": {"edges": [None, 0.0, None], "proportions": [0.1, 0.9]},
        },
    }
    monkeypatch.setattr("app.services.ml_monitoring.settings.ml_drift_window_rows", 200)
    monkeypatch.setattr("app.services.ml_monitoring.settings.ml_drift_min_live_predictions", 30)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        run = MLModelRunORM(
            model_name="logistic_regression", target_name="target_up_5d",
            market_segment="USA", trained_at=start + timedelta(days=3000), dataset_rows=2200,
            metrics_json=json.dumps(metrics), model_path="/model.joblib",
            is_active=True, deployment_role="champion",
        )
        db.add(run)
        for index in range(2200):
            db.add(MLTrainingRowORM(
                asset_id="abc", snapshot_at=start + timedelta(days=index),
                feature_json=json.dumps({"signal": -1.0 if index < 2020 else 1.0}),
                market_segment="USA",
            ))
        db.commit()

        report = _population_stability_report(run, db)

        assert report["source"] == "latest_feature_snapshots"
        assert report["sample_size"] == 200
        assert report["psi"] < 0.2


def test_meta_drift_never_replaces_missing_live_features_with_zero(tmp_path, monkeypatch):
    from app.services.ml_monitoring import _population_stability_report
    from app.services.meta_labeling import META_FEATURE_NAMES

    engine = create_engine(f"sqlite:///{tmp_path / 'meta-drift.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    references = {
        "base": {"edges": [None, 0.0, None], "proportions": [0.5, 0.5]},
        **{
            name: {"edges": [None, 0.5, None], "proportions": [0.5, 0.5]}
            for name in META_FEATURE_NAMES
        },
    }
    monkeypatch.setattr("app.services.ml_monitoring.settings.ml_drift_window_rows", 200)
    monkeypatch.setattr("app.services.ml_monitoring.settings.ml_drift_min_live_predictions", 30)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        run = MLModelRunORM(
            model_name="xgboost", target_name="target_meta_label", asset_id="abc",
            trained_at=start + timedelta(days=300), dataset_rows=200,
            metrics_json=json.dumps({
                "feature_names": ["base", *META_FEATURE_NAMES],
                "feature_reference": references,
            }),
            model_path="/model.joblib", is_active=True, deployment_role="champion",
        )
        db.add(run)
        for index in range(200):
            db.add(MLTrainingRowORM(
                asset_id="abc", snapshot_at=start + timedelta(days=index),
                feature_json=json.dumps({"base": -1.0 if index % 2 else 1.0}),
                market_segment="USA", meta_label_source="heuristic_primary",
            ))
        db.commit()

        report = _population_stability_report(run, db)

        assert report["psi"] < 0.01
        assert report["feature_count"] == 1
        assert set(report["excluded_features"]) == set(META_FEATURE_NAMES)


def test_drift_prefers_features_saved_with_live_predictions(tmp_path, monkeypatch):
    from app.services.ml_monitoring import _population_stability_report

    engine = create_engine(f"sqlite:///{tmp_path / 'prediction-drift.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    metrics = {
        "feature_names": ["signal"],
        "feature_reference": {
            "signal": {"edges": [None, 0.0, None], "proportions": [0.5, 0.5]},
        },
    }
    monkeypatch.setattr("app.services.ml_monitoring.settings.ml_drift_window_rows", 200)
    monkeypatch.setattr("app.services.ml_monitoring.settings.ml_drift_min_live_predictions", 30)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        run = MLModelRunORM(
            model_name="random_forest", target_name="target_up_5d", asset_id="abc",
            trained_at=start, dataset_rows=200, metrics_json=json.dumps(metrics),
            model_path="/model.joblib", is_active=True, deployment_role="champion",
        )
        db.add(run); db.flush()
        for index in range(30):
            db.add(MLPredictionORM(
                asset_id="abc", snapshot_at=start + timedelta(days=index + 1),
                model_run_id=run.id, target_name="target_up_5d",
                probability_up=0.5, predicted_label="up",
                raw_json=json.dumps({"features": {"signal": -1.0 if index % 2 else 1.0}}),
            ))
        db.commit()

        report = _population_stability_report(run, db)

        assert report["source"] == "live_predictions"
        assert report["live_prediction_samples"] == 30
        assert report["psi"] < 0.01


def test_status_exposes_outcome_progress_and_ignores_diagnostic_target(tmp_path):
    from app.services.ml_foundation import status

    engine = create_engine(f"sqlite:///{tmp_path / 'status.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        live_run = _run(now)
        diagnostic_run = _run(now)
        diagnostic_run.target_name = "target_thesis_success"
        db.add_all([live_run, diagnostic_run])
        db.flush()
        db.add(MLModelMonitorORM(
            model_run_id=live_run.id, checked_at=now, asset_id="abc",
            sample_size=7, is_degraded=False, action="keep",
            feature_psi=0.1, calibration_error=0.1,
            recent_avg_net_return_pct=0.4, recent_profit_factor=1.4,
            details_json="{}",
        ))
        db.commit()

        result = status(db)

        assert result.active_models == 1
        assert result.eligible_models == 0
        assert result.outcome_samples == 7
        assert result.min_outcome_samples == 20
        thesis = next(
            target for target in result.targets
            if target.target_name == "target_thesis_success"
        )
        assert thesis.active_models == 1
        assert thesis.shadow_models == 1
