"""XGBoost — purged temporal CV + Optuna tuning bez przecieku."""
from __future__ import annotations

import joblib
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def check_available():
    import xgboost  # noqa — rzuci ImportError jeśli niezainstalowany


def _scale_pos_weight(y: list) -> float:
    import numpy as np
    y_arr = np.array(y)
    neg = max(1, int((y_arr == 0).sum()))
    pos = max(1, int((y_arr == 1).sum()))
    return neg / pos


def _build_model(best_params: dict | None = None, scale: float = 1.0):
    from xgboost import XGBClassifier
    p = best_params or {}
    return XGBClassifier(
        n_estimators=p.get("n_estimators", 300),
        max_depth=p.get("max_depth", 4),
        learning_rate=p.get("learning_rate", 0.05),
        subsample=p.get("subsample", 0.8),
        colsample_bytree=p.get("colsample_bytree", 0.8),
        scale_pos_weight=scale,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )


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

    scale = _scale_pos_weight(y_train)
    base_model = _build_model(best_params, scale)
    base_model.fit(X_train, y_train, eval_set=[(X_cal or X_test, y_cal or y_test)], verbose=False)
    model, calibration_metrics = calibrate_fitted_model(base_model, X_cal or [], y_cal or [])
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1].tolist()

    importances = base_model.get_booster().get_score(importance_type="gain")
    fi = {feature_names[int(k.replace("f", ""))]: float(v)
          for k, v in importances.items() if k.startswith("f")}

    joblib.dump({"model": model, "base_model": base_model, "feature_names": feature_names}, model_path)
    return {
        "accuracy":  float(accuracy_score(y_test, preds)),
        "precision": float(precision_score(y_test, preds, zero_division=0)),
        "recall":    float(recall_score(y_test, preds, zero_division=0)),
        "f1":        float(f1_score(y_test, preds, zero_division=0)),
        "avg_probability_up": float(sum(probs) / len(probs)) if probs else 0.5,
        "feature_importances": fi,
        "best_params": best_params or {},
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
        X, y, groups or list(range(len(X))),
        lambda y_train: _build_model(best_params, _scale_pos_weight(y_train)),
        n_splits=n_splits, purge_sessions=purge_sessions,
    )


def cpcv_score(X: list, y: list, groups: list, purge_sessions: int = 10, best_params: dict | None = None) -> dict:
    from app.services.ml_validation import evaluate_cpcv
    return evaluate_cpcv(
        X, y, groups,
        lambda y_train: _build_model(best_params, _scale_pos_weight(y_train)),
        purge_sessions=purge_sessions,
    )


def optimize(
    X: list, y: list, n_trials: int = 30,
    groups: list | None = None, purge_sessions: int = 20,
) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    from app.services.ml_validation import evaluate_purged_cv
    from xgboost import XGBClassifier

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        }
        result = evaluate_purged_cv(
            X, y, groups or list(range(len(X))),
            lambda y_train: XGBClassifier(
                **params,
                scale_pos_weight=_scale_pos_weight(y_train),
                eval_metric="logloss", random_state=42, n_jobs=-1, verbosity=0,
            ),
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
