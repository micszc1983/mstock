"""Random Forest — Stratified CV + Optuna hyperparameter tuning."""
from __future__ import annotations

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def check_available():
    import sklearn  # noqa


def _build_model(best_params: dict | None = None) -> RandomForestClassifier:
    p = best_params or {}
    return RandomForestClassifier(
        n_estimators=p.get("n_estimators", 300),
        max_depth=p.get("max_depth", 8),
        min_samples_leaf=p.get("min_samples_leaf", 5),
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )


def train(
    X_train: list, y_train: list,
    X_test: list,  y_test: list,
    feature_names: list[str],
    model_path: str,
    best_params: dict | None = None,
) -> dict:
    model = _build_model(best_params)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1].tolist()

    joblib.dump({"model": model, "feature_names": feature_names}, model_path)
    return {
        "accuracy":  float(accuracy_score(y_test, preds)),
        "precision": float(precision_score(y_test, preds, zero_division=0)),
        "recall":    float(recall_score(y_test, preds, zero_division=0)),
        "f1":        float(f1_score(y_test, preds, zero_division=0)),
        "avg_probability_up": float(sum(probs) / len(probs)) if probs else 0.5,
        "feature_importances": dict(zip(feature_names, model.feature_importances_.tolist())),
        "best_params": best_params or {},
    }


def cv_score(
    X: list, y: list,
    feature_names: list[str],  # noqa: ARG001
    n_splits: int = 5,
    best_params: dict | None = None,
) -> dict:
    import numpy as np
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import accuracy_score as _acc, f1_score as _f1

    kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    acc_scores: list[float] = []
    f1_scores:  list[float] = []

    for train_idx, val_idx in kf.split(X, y):
        model = _build_model(best_params)
        model.fit([X[i] for i in train_idx], [y[i] for i in train_idx])
        preds = model.predict([X[i] for i in val_idx])
        y_val = [y[i] for i in val_idx]
        acc_scores.append(float(_acc(y_val, preds)))
        f1_scores.append(float(_f1(y_val, preds, zero_division=0)))

    return {
        "cv_accuracy_mean": round(float(np.mean(acc_scores)), 4),
        "cv_accuracy_std":  round(float(np.std(acc_scores)), 4),
        "cv_f1_mean":       round(float(np.mean(f1_scores)), 4),
        "cv_f1_std":        round(float(np.std(f1_scores)), 4),
        "cv_folds":         n_splits,
    }


def optimize(X: list, y: list, n_trials: int = 30) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    from sklearn.model_selection import StratifiedKFold, cross_val_score

    def objective(trial: optuna.Trial) -> float:
        model = RandomForestClassifier(
            n_estimators=trial.suggest_int("n_estimators", 100, 500, step=50),
            max_depth=trial.suggest_int("max_depth", 3, 15),
            min_samples_leaf=trial.suggest_int("min_samples_leaf", 2, 20),
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        )
        kf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        scores = cross_val_score(model, X, y, cv=kf, scoring="f1", n_jobs=1)
        return float(scores.mean())

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_params


def predict_proba(model_path: str, X: list) -> float:
    bundle = joblib.load(model_path)
    model = bundle["model"]
    feature_names = bundle["feature_names"]
    row = X[-1]
    x = [[float(row.get(k, 0.0)) if isinstance(row, dict) else float(row[i])
          for i, k in enumerate(feature_names)]]
    return float(model.predict_proba(x)[0][1])
