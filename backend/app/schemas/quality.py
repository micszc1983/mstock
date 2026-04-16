from __future__ import annotations

from pydantic import BaseModel


class ThesisQualitySummary(BaseModel):
    asset_id: str
    total_outcomes: int
    directional_accuracy: float
    average_realized_return_pct: float
    bullish_win_rate: float
    bearish_win_rate: float
    flat_rate: float


class ThesisQualityByHorizon(BaseModel):
    asset_id: str
    horizon: str
    total_outcomes: int
    directional_accuracy: float
    average_realized_return_pct: float
    bullish_win_rate: float
    bearish_win_rate: float
    flat_rate: float


class ForecastQualitySummary(BaseModel):
    asset_id: str
    horizon: str
    total_forecasts: int
    average_up_probability: float
    average_down_probability: float
    average_confidence: float
    average_expected_return_pct: float
