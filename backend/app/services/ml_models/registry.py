"""
Centralny rejestr modeli — łączy nazwy z implementacjami.
"""
from __future__ import annotations

import importlib
from typing import Any

# Mapowanie nazwa → moduł.funkcja
_MODEL_REGISTRY: dict[str, str] = {
    "logistic_regression": "app.services.ml_models.logistic",
    "random_forest":       "app.services.ml_models.random_forest",
    "xgboost":             "app.services.ml_models.xgboost_model",
    "lstm":                "app.services.ml_models.lstm_model",
}

# Sprawdź które modele są dostępne (wymagane pakiety zainstalowane)
def _check_available() -> dict[str, bool]:
    available = {}
    for name, module_path in _MODEL_REGISTRY.items():
        try:
            mod = importlib.import_module(module_path)
            mod.check_available()
            available[name] = True
        except Exception:
            available[name] = False
    return available

AVAILABLE_MODELS: list[str] = []

def _refresh_available():
    global AVAILABLE_MODELS
    AVAILABLE_MODELS = [k for k, v in _check_available().items() if v]

_refresh_available()


def train_single_model(
    model_name: str,
    X_train: list,
    y_train: list,
    X_test: list,
    y_test: list,
    feature_names: list[str],
    model_path: str,
    best_params: dict | None = None,
    X_cal: list | None = None,
    y_cal: list | None = None,
) -> dict:
    """Trenuje model o podanej nazwie. Zwraca metryki."""
    if model_name not in _MODEL_REGISTRY:
        raise ValueError(f"Nieznany model: {model_name}. Dostępne: {list(_MODEL_REGISTRY.keys())}")
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    kwargs = {"best_params": best_params}
    if model_name in {"logistic_regression", "random_forest", "xgboost"}:
        kwargs.update({"X_cal": X_cal or [], "y_cal": y_cal or []})
    return mod.train(X_train, y_train, X_test, y_test, feature_names, model_path, **kwargs)


def cv_score_model(
    model_name: str,
    X: list,
    y: list,
    feature_names: list[str],
    n_splits: int = 5,
    best_params: dict | None = None,
    groups: list | None = None,
    purge_sessions: int = 20,
) -> dict | None:
    """Purged grouped temporal CV. Zwraca mean/std accuracy i F1."""
    if model_name not in _MODEL_REGISTRY:
        return None
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    if not hasattr(mod, "cv_score"):
        return None
    return mod.cv_score(
        X, y, feature_names, n_splits=n_splits, best_params=best_params,
        groups=groups, purge_sessions=purge_sessions,
    )


def optimize_model(
    model_name: str,
    X: list,
    y: list,
    n_trials: int = 30,
    groups: list | None = None,
    purge_sessions: int = 20,
) -> dict | None:
    """Optuna hyperparameter search. Zwraca best_params lub None jeśli model nie wspiera."""
    if model_name not in _MODEL_REGISTRY:
        return None
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    if not hasattr(mod, "optimize"):
        return None
    return mod.optimize(
        X, y, n_trials=n_trials, groups=groups, purge_sessions=purge_sessions,
    )


def cpcv_score_model(
    model_name: str, X: list, y: list, groups: list,
    purge_sessions: int = 10, best_params: dict | None = None,
) -> dict:
    if model_name not in _MODEL_REGISTRY:
        return {}
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    if not hasattr(mod, "cpcv_score"):
        return {}
    return mod.cpcv_score(
        X, y, groups, purge_sessions=purge_sessions, best_params=best_params,
    )


def predict_proba_single(model_name: str, model_path: str, X: list) -> float:
    """Wczytuje model i zwraca prawdopodobieństwo klasy UP (1)."""
    if model_name not in _MODEL_REGISTRY:
        raise ValueError(f"Nieznany model: {model_name}")
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    return mod.predict_proba(model_path, X)
