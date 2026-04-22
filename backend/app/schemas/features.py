from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.common import NarrativeLabel, RegimeLabel


class DailyAssetFeatureSnapshot(BaseModel):
    asset_id: str
    snapshot_at: datetime
    last_price: float
    price_change_1d_pct: float
    price_change_5d_pct: float
    price_change_20d_pct: float
    trend_score: float
    sentiment_score: float
    narrative_shift_score: float
    divergence_score: float
    fragility_score: float
    regime_label: RegimeLabel
    regime_confidence: float
    dominant_narrative: Optional[NarrativeLabel]
    volatility_10d: float
    momentum_20d: float
    news_count_7d: int
    implied_volatility: Optional[float] = None   # ATM IV z najbliższej serii opcji (wartość absolutna, np. 0.35 = 35%)
    put_call_ratio: Optional[float] = None       # wolumen put / wolumen call; >1 = bearish, <0.5 = bullish
    iv_rank: Optional[float] = None              # percentyl bieżącego IV w ostatnich 252 dniach (0-100)


class ForecastResponse(BaseModel):
    asset_id: str
    horizon: str
    generated_at: datetime
    direction: str
    up_probability: float
    down_probability: float
    confidence: float
    expected_return_pct: float
    expected_range_low: float
    expected_range_high: float
    model_name: str
    regime_label: RegimeLabel
