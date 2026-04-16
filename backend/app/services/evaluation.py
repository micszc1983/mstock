from __future__ import annotations

import json
from statistics import mean

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sqlalchemy.orm import Session

from app.repositories.decision_support import get_latest_decision_snapshot
from app.repositories.evaluation import insert_strategy_comparison
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.ml import get_active_model_run, insert_backtest_result, list_training_rows_for_target
from app.repositories.outcomes import list_outcomes_for_asset
from app.utils.datetime import now_utc


def run_walkforward_backtest(db: Session, target_name: str = "target_up_5d"):
    rows = list_training_rows_for_target(db, target_name, limit=50000)
    if len(rows) < 30:
        raise ValueError("Not enough rows for walk-forward backtest")

    import json as _json
    results = []
    window = max(20, len(rows) // 5)
    step = max(5, len(rows) // 20)

    for split_end in range(window, len(rows) - step + 1, step):
        train_rows = rows[:split_end]
        test_rows = rows[split_end:split_end + step]
        if not test_rows:
            continue

        feature_names = list(_json.loads(train_rows[0].feature_json).keys())
        X_train = [[float(_json.loads(r.feature_json)[k]) for k in feature_names] for r in train_rows]
        y_train = [int(getattr(r, target_name)) for r in train_rows]
        X_test = [[float(_json.loads(r.feature_json)[k]) for k in feature_names] for r in test_rows]
        y_test = [int(getattr(r, target_name)) for r in test_rows]

        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        probs = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else [0.5] * len(X_test)

        results.append({
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
            "accuracy": float(accuracy_score(y_test, preds)),
            "precision": float(precision_score(y_test, preds, zero_division=0)),
            "recall": float(recall_score(y_test, preds, zero_division=0)),
            "f1": float(f1_score(y_test, preds, zero_division=0)),
            "avg_probability_up": float(mean(probs)) if len(probs) else 0.0,
        })

    summary = {
        "target_name": target_name,
        "windows": len(results),
        "avg_accuracy": float(mean([r["accuracy"] for r in results])) if results else 0.0,
        "avg_precision": float(mean([r["precision"] for r in results])) if results else 0.0,
        "avg_recall": float(mean([r["recall"] for r in results])) if results else 0.0,
        "avg_f1": float(mean([r["f1"] for r in results])) if results else 0.0,
        "windows_detail": results,
    }

    active = get_active_model_run(db, target_name)
    model_run_id = active.id if active else 0
    row = insert_backtest_result(db, model_run_id=model_run_id, result_json=json.dumps(summary, ensure_ascii=False))
    db.commit()
    db.refresh(row)
    return row


def compare_heuristic_vs_ml_for_asset(db: Session, asset_id: str):
    outcomes = {row.horizon: row for row in list_outcomes_for_asset(db, asset_id, limit=300)}
    feature = get_latest_feature_snapshot(db, asset_id)
    decision = get_latest_decision_snapshot(db, asset_id)
    active_model = get_active_model_run(db, "target_up_5d")

    sample_size = len(outcomes)
    if feature is None or decision is None or sample_size == 0:
        raise ValueError("Not enough data to compare heuristic vs ML")

    # heuristic proxy: positive net thesis edge + decent conviction
    heuristic_up = 1 if (decision.net_thesis_edge > 0 and decision.conviction_score >= 50) else 0
    actual_up_5d = 1 if ("5d" in outcomes and outcomes["5d"].realized_return_pct > 0) else 0
    heuristic_accuracy = 1.0 if heuristic_up == actual_up_5d else 0.0
    heuristic_avg_return = outcomes["5d"].realized_return_pct if "5d" in outcomes and heuristic_up == 1 else 0.0

    ml_accuracy = 0.0
    ml_avg_return = 0.0
    better_mode = "heuristic"

    if active_model is not None:
        bundle = joblib.load(active_model.model_path)
        model = bundle["model"]
        feature_names = bundle["feature_names"]
        vec = {
            "last_price": feature.last_price,
            "trend_score": feature.trend_score,
            "sentiment_score": feature.sentiment_score,
            "divergence_score": feature.divergence_score,
            "fragility_score": feature.fragility_score,
            "narrative_shift_score": feature.narrative_shift_score,
            "forecast_confidence_1d": 50.0,
            "forecast_up_probability_1d": 50.0,
            "decision_conviction": decision.conviction_score,
            "decision_risk": decision.risk_score,
            "decision_timing": decision.timing_score,
            "decision_setup_quality": decision.setup_quality_score,
        }
        X = [[float(vec[k]) for k in feature_names]]
        prob = float(model.predict_proba(X)[0][1]) if hasattr(model, "predict_proba") else 0.5
        ml_up = 1 if prob >= 0.5 else 0
        ml_accuracy = 1.0 if ml_up == actual_up_5d else 0.0
        ml_avg_return = outcomes["5d"].realized_return_pct if "5d" in outcomes and ml_up == 1 else 0.0
        better_mode = "ml" if ml_accuracy > heuristic_accuracy or (ml_accuracy == heuristic_accuracy and ml_avg_return > heuristic_avg_return) else "heuristic"

    row = insert_strategy_comparison(
        db=db,
        asset_id=asset_id,
        heuristic_accuracy_5d=heuristic_accuracy,
        ml_accuracy_5d=ml_accuracy,
        heuristic_avg_return_5d=heuristic_avg_return,
        ml_avg_return_5d=ml_avg_return,
        better_mode=better_mode,
        sample_size=sample_size,
    )
    db.commit()
    db.refresh(row)
    return row
