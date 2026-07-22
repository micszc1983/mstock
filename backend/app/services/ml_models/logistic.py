"""Logistic Regression — purged temporal CV + Optuna tuning bez przecieku."""
from __future__ import annotations

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def check_available():
    import sklearn  # noqa


def _build_pipeline(best_params: dict | None = None) -> Pipeline:
    p = best_params or {}
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            C=p.get("C", 0.5),
            solver=p.get("solver", "lbfgs"),
        )),
    ])


def train(
    X_train: list, y_train: list,
    X_test: list,  y_test: list,
    feature_names: list[str],
    model_path: str,
    best_params: dict | None = None,
    X_cal: list | None = None,
    y_cal: list | None = None,
) -> dict:
    from app.services.ml_models.calibration import calibrate_fitted_model

    base_model = _build_pipeline(best_params)
    base_model.fit(X_train, y_train)
    model, calibration_metrics = calibrate_fitted_model(base_model, X_cal or [], y_cal or [])
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1].tolist()

    joblib.dump({"model": model, "base_model": base_model, "feature_names": feature_names}, model_path)
    return {
        "accuracy":  float(accuracy_score(y_test, preds)),
        "precision": float(precision_score(y_test, preds, zero_division=0)),
        "recall":    float(recall_score(y_test, preds, zero_division=0)),
        "f1":        float(f1_score(y_test, preds, zero_division=0)),
        "avg_probability_up": float(sum(probs) / len(probs)) if probs else 0.5,
        "best_params": best_params or {"C": 0.5, "solver": "lbfgs"},
        **calibration_metrics,
    }


def cv_score(
    X: list, y: list,
    feature_names: list[str],  # noqa: ARG001
    n_splits: int = 5,
    best_params: dict | None = None,
    groups: list | None = None,
    purge_sessions: int = 20,
) -> dict:
    from app.services.ml_validation import evaluate_purged_cv
    return evaluate_purged_cv(
        X, y, groups or list(range(len(X))), lambda _y: _build_pipeline(best_params),
        n_splits=n_splits, purge_sessions=purge_sessions,
    )


def cpcv_score(X: list, y: list, groups: list, purge_sessions: int = 10, best_params: dict | None = None) -> dict:
    from app.services.ml_validation import evaluate_cpcv
    return evaluate_cpcv(
        X, y, groups, lambda _y: _build_pipeline(best_params), purge_sessions=purge_sessions,
    )


def optimize(
    X: list, y: list, n_trials: int = 30,
    groups: list | None = None, purge_sessions: int = 20,
) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    from app.services.ml_validation import evaluate_purged_cv

    def objective(trial: optuna.Trial) -> float:
        params = {
            "C": trial.suggest_float("C", 1e-3, 10.0, log=True),
            "solver": trial.suggest_categorical("solver", ["lbfgs", "liblinear"]),
        }
        result = evaluate_purged_cv(
            X, y, groups or list(range(len(X))), lambda _y: _build_pipeline(params),
            n_splits=3, purge_sessions=purge_sessions,
        )
        return float(result.get("cv_f1_mean", 0.0))

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
