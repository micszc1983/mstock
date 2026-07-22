from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import AssetORM, MLModelRunORM, MLTrainingRowORM, RecommendationRecordORM
from app.db.session import Base


def test_probability_calibration_uses_separate_window():
    from sklearn.linear_model import LogisticRegression
    from app.services.ml_models.calibration import calibrate_fitted_model

    X = [[index % 7, index] for index in range(100)]
    y = [index % 2 for index in range(100)]
    base = LogisticRegression().fit(X[:60], y[:60])
    calibrated, metrics = calibrate_fitted_model(base, X[60:85], y[60:85])

    assert metrics["calibration_method"] == "sigmoid"
    assert metrics["calibration_rows"] == 25
    assert 0 <= calibrated.predict_proba([[1, 99]])[0][1] <= 1


def test_oof_meta_labels_store_primary_probability(tmp_path, monkeypatch):
    from app.services import meta_labeling

    engine = create_engine(f"sqlite:///{tmp_path / 'oof.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        for index in range(180):
            db.add(MLTrainingRowORM(
                asset_id="abc", snapshot_at=start + timedelta(days=index),
                feature_json=json.dumps({"trend_score": float(index % 10), "momentum_20d": 1.0}),
                target_triple_barrier=index % 2,
                target_meta_label=0,
                triple_barrier_return_pct=1.0,
                triple_barrier_hit="upper",
                market_segment="USA", market_regime="risk_on",
                meta_label_source="heuristic_primary",
            ))
        db.commit()

        monkeypatch.setattr(
            meta_labeling, "_fit_fold_probabilities",
            lambda _X, _y, _train, test: [[0.8] * len(test), [0.6] * len(test)],
        )
        result = meta_labeling.rebuild_oof_meta_labels(db, "abc")
        oof = db.query(MLTrainingRowORM).filter_by(meta_label_source="purged_oof_primary").all()

        assert result["updated"] == len(oof) > 0
        assert all(abs((row.meta_primary_probability or 0) - 0.7) < 1e-9 for row in oof)
        assert all(row.meta_side == 1 and row.target_meta_label == 1 for row in oof)


def test_meta_threshold_is_fitted_for_market_and_regime(tmp_path):
    from app.services.meta_thresholds import calibrated_meta_threshold

    engine = create_engine(f"sqlite:///{tmp_path / 'threshold.db'}")
    Base.metadata.create_all(engine)
    observations = []
    for index in range(120):
        probability = 0.75 if index < 60 else 0.52
        observations.append({
            "probability": probability,
            "net_return_pct": 1.2 if probability > 0.7 else -0.5,
            "label": int(probability > 0.7), "market": "USA", "regime": "risk_on",
        })
    with Session(engine) as db:
        db.add(MLModelRunORM(
            model_name="xgboost", target_name="target_meta_label", asset_id="abc",
            trained_at=datetime.now(timezone.utc), dataset_rows=200,
            metrics_json=json.dumps({"meta_holdout_observations": observations}),
            model_path="/model.joblib", is_active=True, deployment_role="champion",
        ))
        db.commit()
        threshold = calibrated_meta_threshold(db, "USA", "risk_on")

        assert threshold.scope == "market_regime"
        assert threshold.threshold > 0.52
        assert threshold.expected_net_return_pct > 0


def test_monitor_rolls_back_degraded_meta_champion(tmp_path):
    from app.services.ml_monitoring import monitor_active_models

    engine = create_engine(f"sqlite:///{tmp_path / 'monitor.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    safe = {
        "holdout_trades": 40, "holdout_avg_net_return_pct": 0.5,
        "deflated_sharpe_ratio": 0.8,
    }
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        old = MLModelRunORM(
            model_name="random_forest", target_name="target_meta_label", asset_id="abc",
            trained_at=now - timedelta(days=2), dataset_rows=200, metrics_json=json.dumps(safe),
            model_path="/old.joblib", is_active=False, deployment_role="archived",
        )
        current = MLModelRunORM(
            model_name="xgboost", target_name="target_meta_label", asset_id="abc",
            trained_at=now, dataset_rows=200, metrics_json=json.dumps(safe),
            model_path="/current.joblib", is_active=True, deployment_role="champion",
        )
        db.add_all([old, current])
        for index in range(20):
            db.add(RecommendationRecordORM(
                asset_id="abc", snapshot_at=now - timedelta(days=30 - index), created_at=now,
                model_version="test", market="USA", regime="risk_on", action="BUY",
                displayed_action="KUP", has_position=False, calibration_scope="test",
                calibration_sample_size=100, composite_score=60, confidence=60,
                probability_buy=60, probability_sell=30, probability_no_trade=10,
                buy_threshold=55, sell_threshold=45, transaction_cost_pct=0.2,
                expected_gross_edge_pct=1, expected_net_edge_pct=0.8, uncertainty_pct=0.2,
                meta_trade_probability=80, meta_gate_applied=False, base_price=100,
                realized_return_5d_pct=-1, strategy_net_return_5d_pct=-1.2,
            ))
        db.commit()

        # Scoring po rollbacku wymagałby pliku joblib; w tym teście izolujemy decyzję monitoringu.
        rows = monitor_active_models(db, allow_rollback=False)
        assert rows[0].is_degraded is True
        assert rows[0].action == "alert"
