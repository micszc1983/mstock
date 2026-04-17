from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


# Targety obsługiwane przez system ML
ML_TARGETS: list[str] = ["target_up_5d", "target_up_20d", "target_thesis_success"]

ML_TARGET_LABELS: dict[str, str] = {
    "target_up_5d":          "Kierunek 5d",
    "target_up_20d":         "Kierunek 20d",
    "target_thesis_success": "Skuteczność tezy",
}

ML_TARGET_DESCRIPTIONS: dict[str, str] = {
    "target_up_5d":          "Czy cena wzrośnie w ciągu 5 dni?",
    "target_up_20d":         "Czy cena wzrośnie w ciągu 20 dni?",
    "target_thesis_success":  "Czy teza okazała się kierunkowo poprawna po 5 dniach?",
}


class MLActiveModel(BaseModel):
    target_name: str
    target_label: str
    model_name: Optional[str] = None
    is_trained: bool = False
    dataset_rows: int = 0


class MLStatusResponse(BaseModel):
    ml_mode: str
    ml_enabled: bool
    # zachowane dla kompatybilności
    active_model_name: Optional[str] = None
    active_target_name: Optional[str] = None
    dataset_rows: int
    min_training_rows: int
    ready_for_training: bool
    # nowe: stan każdego targetu
    targets: list[MLActiveModel] = []


class MLModeUpdate(BaseModel):
    ml_enabled: bool


class MLDatasetBuildResponse(BaseModel):
    built_rows: int
    total_rows: int


class MLDatasetStatsResponse(BaseModel):
    total_rows: int
    assets: Dict[str, int]
    labeled_rows_1d: int
    labeled_rows_5d: int
    labeled_rows_20d: int
    thesis_success_rows: int


class MLTrainRequest(BaseModel):
    target_name: str = "target_up_5d"
    model_name: str = "logistic_regression"
    asset_id: str | None = None


class MLModelRunResponse(BaseModel):
    id: int
    model_name: str
    target_name: str
    trained_at: datetime
    dataset_rows: int
    metrics_json: str
    model_path: str
    is_active: bool


class MLBacktestResponse(BaseModel):
    model_run_id: int
    created_at: datetime
    result_json: str


class MLPredictionResponse(BaseModel):
    asset_id: str
    snapshot_at: datetime
    model_run_id: int
    target_name: str
    probability_up: float
    predicted_label: str
    raw_json: str


class MLFeatureImportance(BaseModel):
    feature: str
    importance: float          # abs(coef) — globalna waga cechy w modelu
    direction: str             # "bullish" | "bearish" — kierunek koef

class MLPredictionContribution(BaseModel):
    feature: str
    feature_value: float       # surowa wartość cechy dla tego aktywa
    contribution: float        # coef * feature_value → wkład do log-odds
    direction: str             # "bullish" | "bearish"

class MLExplanationResponse(BaseModel):
    asset_id: str
    target_name: str
    probability_up: float
    predicted_label: str       # "up" | "down"
    interpretation: str        # np. "Model jest bullish głównie przez trend i conviction."
    feature_importances: list[MLFeatureImportance]      # globalne wagi (top-down abs)
    prediction_contributions: list[MLPredictionContribution]  # wkłady dla tej konkretnej predykcji
