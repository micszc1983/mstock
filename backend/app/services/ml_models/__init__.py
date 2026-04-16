"""
Pakiet modeli ML. Każdy moduł implementuje train() i predict_proba().
Import jest leniwy — brakujące pakiety (xgboost, torch) nie blokują startu.
"""
from .registry import AVAILABLE_MODELS, train_single_model, predict_proba_single

__all__ = ["AVAILABLE_MODELS", "train_single_model", "predict_proba_single"]
