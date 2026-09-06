from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PriceQuality(BaseModel):
    total_points: int
    last_timestamp: Optional[datetime]
    staleness_hours: Optional[float]        # ile godzin temu ostatnia cena
    is_stale: bool                          # >48h dla stocks, >72h dla metali
    gap_count: int                          # ile brakujących dni roboczych
    gap_pct: float                          # % brakujących dni
    score: float                            # 0-1


class NewsQuality(BaseModel):
    total_items: int
    items_7d: int
    items_30d: int
    last_timestamp: Optional[datetime]
    staleness_hours: Optional[float]
    is_stale: bool                          # >72h bez newsów
    nlp_enriched: int                       # ile ma NLP run
    nlp_coverage_pct: float                 # % z NLP
    nlp_model: str
    current_model_items_30d: int
    current_model_coverage_30d_pct: float
    relevant_items_7d: int
    relevance_mean_7d: float
    low_relevance_pct_7d: float
    source_count_7d: int
    score: float


class FeatureQuality(BaseModel):
    has_snapshot: bool
    staleness_hours: Optional[float]
    is_stale: bool
    scores_nonzero: bool                    # czy nie wszystkie zera
    has_all_forecasts: bool                 # 1d + 5d + 20d
    has_decision_snapshot: bool
    score: float


class MLQuality(BaseModel):
    training_rows: int
    labeled_rows_5d: int
    labeled_rows_20d: int
    labeled_rows_thesis: int
    label_coverage_pct: float               # labeled/total
    min_required: int
    ready_for_training: bool
    score: float


class SyncQuality(BaseModel):
    errors_24h: int
    errors_7d: int
    total_syncs_7d: int
    error_rate_7d: float                    # errors/total
    last_successful_sync: Optional[datetime]
    last_error: Optional[str]
    score: float


class AssetDataQuality(BaseModel):
    asset_id: str
    name: str
    symbol: str
    asset_type: str

    # Wymiary jakości
    prices:   PriceQuality
    news:     NewsQuality
    features: FeatureQuality
    ml:       MLQuality
    sync:     SyncQuality

    # Wynik zbiorczy
    overall_score: float                    # 0-1 (ważona średnia)
    grade: str                              # "A" "B" "C" "D" "F"
    grade_label: str                        # "Dobry" / "Przeciętny" / "Słaby" / "Krytyczny"
    issues: list[str]                       # konkretne problemy
    warnings: list[str]                     # ostrzeżenia
    checked_at: datetime


class DataQualityReport(BaseModel):
    assets: list[AssetDataQuality]
    checked_at: datetime
    summary: dict                           # aggregate stats
