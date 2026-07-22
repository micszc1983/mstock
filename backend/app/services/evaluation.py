from __future__ import annotations

import json
from datetime import datetime
from statistics import mean

from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sqlalchemy.orm import Session

from app.repositories.decision_support import get_latest_decision_snapshot
from app.repositories.evaluation import insert_strategy_comparison
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.ml import (
    get_all_active_model_runs,
    insert_backtest_result,
    list_training_rows_for_target,
)
from app.repositories.outcomes import list_outcomes_for_asset
from app.services.ml_models.registry import predict_proba_single


def run_walkforward_backtest(db: Session, target_name: str = "target_up_5d", asset_id: str | None = None):
    """
    Walk-forward backtest dla danego targetu i aktywa.
    Testuje każdy dostępny aktywny model (przez registry) osobno i w ensemble.
    """
    rows = list_training_rows_for_target(db, target_name, asset_id=asset_id, limit=50000)
    if len(rows) < 30:
        raise ValueError("Not enough rows for walk-forward backtest")

    import json as _json
    from app.services.ml_models.registry import AVAILABLE_MODELS, train_single_model
    import tempfile, os

    models_to_test = AVAILABLE_MODELS if AVAILABLE_MODELS else ["logistic_regression"]
    window = max(20, len(rows) // 5)
    step = max(5, len(rows) // 20)

    # Wyniki per model: {model_name: [{"accuracy":..., ...}, ...]}
    per_model_results: dict[str, list[dict]] = {m: [] for m in models_to_test}
    ensemble_results: list[dict] = []

    horizon_gap = 20 if target_name == "target_up_20d" else 5
    for split_end in range(window, len(rows) - step + 1, step):
        # Embargo usuwa z treningu etykiety, których horyzont nachodzi na test.
        train_rows = rows[:max(0, split_end - horizon_gap)]
        test_rows = rows[split_end:split_end + step]
        if len(train_rows) < 20 or not test_rows:
            continue

        feature_names = list(_json.loads(train_rows[0].feature_json).keys())
        X_train = [[float(_json.loads(r.feature_json).get(k, 0.0)) for k in feature_names] for r in train_rows]
        y_train = [int(getattr(r, target_name)) for r in train_rows if getattr(r, target_name) is not None]
        X_test  = [[float(_json.loads(r.feature_json).get(k, 0.0)) for k in feature_names] for r in test_rows]
        y_test  = [int(getattr(r, target_name)) for r in test_rows  if getattr(r, target_name) is not None]

        if len(set(y_train)) < 2 or not y_test:
            continue

        window_probs: dict[str, list[float]] = {}
        for model_name in models_to_test:
            try:
                with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tf:
                    tmp_path = tf.name
                try:
                    train_single_model(model_name, X_train, y_train, X_test, y_test, feature_names, tmp_path)
                    import joblib
                    bundle = joblib.load(tmp_path)
                    model = bundle["model"]
                    preds = [int(p) for p in model.predict(X_test)]
                    probs = [float(p) for p in model.predict_proba(X_test)[:, 1]] if hasattr(model, "predict_proba") else [0.5] * len(X_test)
                    per_model_results[model_name].append({
                        "train_rows": len(train_rows),
                        "test_rows": len(test_rows),
                        "accuracy":  float(accuracy_score(y_test, preds)),
                        "precision": float(precision_score(y_test, preds, zero_division=0)),
                        "recall":    float(recall_score(y_test, preds, zero_division=0)),
                        "f1":        float(f1_score(y_test, preds, zero_division=0)),
                        "avg_prob_up": float(mean(probs)),
                    })
                    window_probs[model_name] = probs
                finally:
                    os.unlink(tmp_path)
            except Exception:
                pass

        # Ensemble: uśrednij predykcje modeli które udało się wytrenować
        if window_probs:
            ens_probs = [mean(window_probs[m][i] for m in window_probs) for i in range(len(y_test))]
            ens_preds = [1 if p >= 0.5 else 0 for p in ens_probs]
            ensemble_results.append({
                "train_rows": len(train_rows),
                "test_rows": len(test_rows),
                "accuracy":  float(accuracy_score(y_test, ens_preds)),
                "precision": float(precision_score(y_test, ens_preds, zero_division=0)),
                "recall":    float(recall_score(y_test, ens_preds, zero_division=0)),
                "f1":        float(f1_score(y_test, ens_preds, zero_division=0)),
                "avg_prob_up": float(mean(ens_probs)),
            })

    def _summarize(wnd: list[dict]) -> dict:
        if not wnd:
            return {"windows": 0, "avg_accuracy": 0.0, "avg_precision": 0.0, "avg_recall": 0.0, "avg_f1": 0.0}
        return {
            "windows":       len(wnd),
            "avg_accuracy":  round(float(mean(w["accuracy"]  for w in wnd)), 4),
            "avg_precision": round(float(mean(w["precision"] for w in wnd)), 4),
            "avg_recall":    round(float(mean(w["recall"]    for w in wnd)), 4),
            "avg_f1":        round(float(mean(w["f1"]        for w in wnd)), 4),
        }

    summary = {
        "target_name": target_name,
        "asset_id": asset_id,
        "total_rows": len(rows),
        "models": {m: _summarize(per_model_results[m]) for m in models_to_test},
        "ensemble": _summarize(ensemble_results),
        "windows_detail": ensemble_results,
    }

    # Powiąż z pierwszym aktywnym modelem dla danego targetu/aktywa
    runs = get_all_active_model_runs(db, target_name, asset_id=asset_id)
    if not runs:
        runs = get_all_active_model_runs(db, target_name, asset_id=None)
    model_run_id = runs[0].id if runs else 0
    row = insert_backtest_result(db, model_run_id=model_run_id, result_json=json.dumps(summary, ensure_ascii=False))
    db.commit()
    db.refresh(row)
    return row


def compare_heuristic_vs_ml_for_asset(db: Session, asset_id: str):
    """
    Porównuje heurystykę z ML ensemble na historycznych outcomeach.
    Używa wszystkich aktywnych modeli (per-asset + globalnych) przez registry.
    """
    target_name = "target_up_5d"
    per_asset = get_all_active_model_runs(db, target_name, asset_id=asset_id)
    global_runs = get_all_active_model_runs(db, target_name, asset_id=None)
    per_asset_names = {r.model_name for r in per_asset}
    active_runs = list(per_asset) + [r for r in global_runs if r.model_name not in per_asset_names]

    if not active_runs:
        raise ValueError("No active ML model for comparison")

    # Każdy porównywany rekord musi być późniejszy od treningu wszystkich modeli.
    from app.utils.datetime import ensure_utc
    cutoffs = []
    valid_runs = []
    for run in active_runs:
        try:
            metadata = json.loads(run.metrics_json)
            cutoffs.append(ensure_utc(datetime.fromisoformat(metadata["train_end"])))
            valid_runs.append(run)
        except (KeyError, TypeError, ValueError):
            continue
    if not valid_runs:
        raise ValueError("Active models lack temporal holdout metadata; retrain first")
    common_cutoff = max(cutoffs)

    hist = list_training_rows_for_target(db, target_name, asset_id=asset_id, limit=1000)
    labeled = [r for r in hist if ensure_utc(r.snapshot_at) > common_cutoff and r.target_return_5d is not None]
    if not labeled:
        raise ValueError("No common out-of-sample rows for comparison")

    # Outcome heurystyki powiązany z dokładnie tym samym snapshotem i horyzontem.
    from sqlalchemy import select, func
    from app.db.models import ThesisORM, ThesisOutcomeORM
    outcome_rows = db.execute(
        select(ThesisORM.source_snapshot_at, ThesisOutcomeORM)
        .join(ThesisOutcomeORM, ThesisOutcomeORM.thesis_id == ThesisORM.id)
        .where(ThesisORM.asset_id == asset_id, ThesisOutcomeORM.horizon == "5d")
    ).all()
    heuristic_by_date = {source.date(): outcome for source, outcome in outcome_rows}

    ml_correct = 0
    ml_returns = []
    heuristic_correct = 0
    heuristic_returns = []
    for training_row in labeled:
        heuristic = heuristic_by_date.get(training_row.snapshot_at.date())
        if heuristic is None:
            continue
        probabilities = []
        features = [json.loads(training_row.feature_json)]
        for run in valid_runs:
            try:
                probabilities.append(predict_proba_single(run.model_name, run.model_path, features))
            except Exception:
                continue
        if not probabilities:
            continue
        predicts_up = mean(probabilities) >= 0.5
        actual_return = float(training_row.target_return_5d)
        ml_correct += int(predicts_up == (actual_return > 0))
        ml_returns.append(actual_return if predicts_up else -actual_return)
        heuristic_correct += int(heuristic.was_directionally_correct)
        heuristic_returns.append(abs(actual_return) if heuristic.was_directionally_correct else -abs(actual_return))

    sample_size = len(ml_returns)
    if sample_size == 0:
        raise ValueError("No aligned out-of-sample observations for comparison")
    ml_accuracy = ml_correct / sample_size
    heuristic_accuracy = heuristic_correct / sample_size
    ml_avg_return = mean(ml_returns)
    heuristic_avg_return = mean(heuristic_returns)
    better_mode = "ml" if (ml_accuracy, ml_avg_return) > (heuristic_accuracy, heuristic_avg_return) else "heuristic"

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
