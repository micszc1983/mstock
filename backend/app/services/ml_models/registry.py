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
) -> dict:
    """
    Trenuje model o podanej nazwie. Zwraca metryki.
    Rzuca ImportError jeśli model niedostępny, ValueError jeśli nieznany.
    """
    if model_name not in _MODEL_REGISTRY:
        raise ValueError(f"Nieznany model: {model_name}. Dostępne: {list(_MODEL_REGISTRY.keys())}")
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    return mod.train(X_train, y_train, X_test, y_test, feature_names, model_path)


def predict_proba_single(model_name: str, model_path: str, X: list) -> float:
    """Wczytuje model i zwraca prawdopodobieństwo klasy UP (1)."""
    if model_name not in _MODEL_REGISTRY:
        raise ValueError(f"Nieznany model: {model_name}")
    mod = importlib.import_module(_MODEL_REGISTRY[model_name])
    return mod.predict_proba(model_path, X)
