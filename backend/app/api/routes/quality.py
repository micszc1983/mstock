from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset
from app.schemas.quality import ForecastQualitySummary, ThesisQualityByHorizon, ThesisQualitySummary
from app.services.quality_metrics import (
    build_forecast_quality_summary,
    build_thesis_quality_by_horizon,
    build_thesis_quality_summary,
)
from app.repositories.prices import list_prices
from app.services.ohlcv_validation import validate_series

router = APIRouter(tags=["quality"])


def _ensure_asset_exists(db: Session, asset_id: str) -> None:
    row = get_asset(db, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")


@router.get("/assets/{asset_id}/quality/thesis/summary", response_model=ThesisQualitySummary)
def thesis_quality_summary(asset_id: str, limit: int = Query(default=500, ge=1, le=5000), db: Session = Depends(get_db)) -> ThesisQualitySummary:
    _ensure_asset_exists(db, asset_id)
    return build_thesis_quality_summary(db, asset_id, limit=limit)


@router.get("/assets/{asset_id}/quality/thesis/by-horizon", response_model=list[ThesisQualityByHorizon])
def thesis_quality_by_horizon(asset_id: str, limit: int = Query(default=500, ge=1, le=5000), db: Session = Depends(get_db)) -> list[ThesisQualityByHorizon]:
    _ensure_asset_exists(db, asset_id)
    return build_thesis_quality_by_horizon(db, asset_id, limit=limit)


@router.get("/assets/{asset_id}/quality/forecast/summary", response_model=list[ForecastQualitySummary])
def forecast_quality_summary(asset_id: str, limit: int = Query(default=500, ge=1, le=5000), db: Session = Depends(get_db)) -> list[ForecastQualitySummary]:
    _ensure_asset_exists(db, asset_id)
    return build_forecast_quality_summary(db, asset_id, limit=limit)


@router.get("/assets/{asset_id}/quality/ohlcv")
def ohlcv_quality(asset_id: str, limit: int = Query(default=500, ge=20, le=5000), db: Session = Depends(get_db)) -> dict:
    _ensure_asset_exists(db, asset_id)
    return {"asset_id": asset_id, **validate_series(list_prices(db, asset_id, limit=limit))}
