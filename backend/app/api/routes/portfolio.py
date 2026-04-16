from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio import AggregateDashboardResponse, CompareAssetsResponse
from app.services.aggregate_dashboard import build_asset_overview_for_ids, compare_assets

router = APIRouter(tags=["portfolio"])


@router.get("/dashboard/aggregate", response_model=AggregateDashboardResponse)
def aggregate_dashboard(asset_ids: str = Query(...), db: Session = Depends(get_db)) -> AggregateDashboardResponse:
    ids = [item.strip().lower() for item in asset_ids.split(",") if item.strip()]
    return AggregateDashboardResponse(asset_ids=ids, rows=build_asset_overview_for_ids(db, ids))


@router.get("/compare/assets", response_model=CompareAssetsResponse)
def compare_assets_endpoint(asset_ids: str = Query(...), db: Session = Depends(get_db)) -> CompareAssetsResponse:
    ids = [item.strip().lower() for item in asset_ids.split(",") if item.strip()]
    return compare_assets(db, ids)
