from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import feature_to_schema, forecast_to_schema
from app.repositories.assets import get_asset, list_assets
from app.repositories.features import get_latest_feature_snapshot, list_feature_history
from app.repositories.forecasts import get_latest_forecasts, list_forecast_history
from app.schemas.features import DailyAssetFeatureSnapshot, ForecastResponse
from app.services.feature_builder import rebuild_all_features_and_forecasts

router = APIRouter(tags=["features"])


def _ensure_asset_exists(db: Session, asset_id: str):
    row = get_asset(db, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return row


@router.post("/features/rebuild")
def rebuild_features(db: Session = Depends(get_db)) -> dict[str, int]:
    assets = list_assets(db)
    built = rebuild_all_features_and_forecasts(db, assets)
    return {"rebuilt_assets": built}


@router.get("/assets/{asset_id}/features/latest", response_model=DailyAssetFeatureSnapshot)
def get_features_latest(asset_id: str, db: Session = Depends(get_db)) -> DailyAssetFeatureSnapshot:
    row = _ensure_asset_exists(db, asset_id)
    item = get_latest_feature_snapshot(db, asset_id)
    if item is None:
        rebuild_all_features_and_forecasts(db, [row])
        item = get_latest_feature_snapshot(db, asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No features for {asset_id}")
    return feature_to_schema(item)


@router.get("/assets/{asset_id}/features/history", response_model=list[DailyAssetFeatureSnapshot])
def get_features_history(asset_id: str, limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[DailyAssetFeatureSnapshot]:
    row = _ensure_asset_exists(db, asset_id)
    items = list_feature_history(db, asset_id, limit=limit)
    if not items:
        rebuild_all_features_and_forecasts(db, [row])
        items = list_feature_history(db, asset_id, limit=limit)
    return [feature_to_schema(item) for item in items]


@router.get("/assets/{asset_id}/forecast", response_model=list[ForecastResponse])
def get_forecast_latest(asset_id: str, db: Session = Depends(get_db)) -> list[ForecastResponse]:
    row = _ensure_asset_exists(db, asset_id)
    items = get_latest_forecasts(db, asset_id)
    if not items:
        rebuild_all_features_and_forecasts(db, [row])
        items = get_latest_forecasts(db, asset_id)
    return [forecast_to_schema(item) for item in items]


@router.get("/assets/{asset_id}/forecast/history", response_model=list[ForecastResponse])
def get_forecast_history(
    asset_id: str,
    horizon: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[ForecastResponse]:
    row = _ensure_asset_exists(db, asset_id)
    items = list_forecast_history(db, asset_id, horizon=horizon, limit=limit)
    if not items:
        rebuild_all_features_and_forecasts(db, [row])
        items = list_forecast_history(db, asset_id, horizon=horizon, limit=limit)
    return [forecast_to_schema(item) for item in items]
