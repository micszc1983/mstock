from __future__ import annotations

from typing import List

from pydantic import BaseModel

from app.schemas.thesis import AssetOverview


class AggregateDashboardResponse(BaseModel):
    asset_ids: List[str]
    rows: List[AssetOverview]


class CompareAssetRow(BaseModel):
    asset_id: str
    last_price: float
    trend_score: float
    sentiment_score: float
    divergence_score: float
    fragility_score: float
    regime: str
    dominant_narrative: str | None
    forecast_direction_1d: str | None
    forecast_confidence_1d: float | None


class CompareAssetsResponse(BaseModel):
    asset_ids: List[str]
    rows: List[CompareAssetRow]
