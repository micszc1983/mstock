from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import asset_to_schema, price_to_schema
from app.repositories.assets import list_assets
from app.repositories.prices import list_prices
from app.schemas.thesis import AssetOverview
from app.services.analytics import build_overview
from app.services.news_features import list_news_for_analysis

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=list[AssetOverview])
def dashboard(db: Session = Depends(get_db)) -> list[AssetOverview]:
    results: list[AssetOverview] = []
    for asset_row in list_assets(db):
        prices = [price_to_schema(row) for row in list_prices(db, asset_row.id)]
        if len(prices) < 21:
            continue
        news = list_news_for_analysis(db, asset_row.id)
        results.append(build_overview(asset_to_schema(asset_row), prices, news))
    return results
