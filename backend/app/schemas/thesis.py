from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.asset import Asset
from app.schemas.common import NarrativeLabel, RegimeLabel


class AssetOverview(BaseModel):
    asset: Asset
    last_price: float
    price_change_1d_pct: float
    price_change_5d_pct: float
    price_change_20d_pct: float
    trend_score: float
    sentiment_score: float
    narrative_shift_score: float
    divergence_score: float
    fragility_score: float
    regime: RegimeLabel
    regime_confidence: float
    dominant_narrative: Optional[NarrativeLabel]


class ThesisResponse(BaseModel):
    asset_id: str
    generated_at: datetime
    regime: RegimeLabel
    regime_confidence: float
    dominant_narrative: Optional[NarrativeLabel]
    thesis_confidence: float
    fragility_score: float
    divergence_score: float
    thesis: str
    anti_thesis: str
    support_factors: List[str]
    risk_factors: List[str]
    invalidation_conditions: List[str]


class StoredThesisResponse(ThesisResponse):
    id: int
    source_snapshot_at: datetime
    model_name: str


class BreakMonitorItem(BaseModel):
    condition: str
    current_value: str
    status: str
    severity: str


class BreakMonitorResponse(BaseModel):
    asset_id: str
    generated_at: datetime
    items: List[BreakMonitorItem]
