from __future__ import annotations

from sqlalchemy.orm import Session

from app.mappers import asset_to_schema, news_to_schema, price_to_schema
from app.repositories.assets import get_asset
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.news import list_news
from app.repositories.prices import list_prices
from app.schemas.portfolio import CompareAssetRow, CompareAssetsResponse
from app.schemas.thesis import AssetOverview
from app.services.analytics import build_overview


def build_asset_overview_for_ids(db: Session, asset_ids: list[str]) -> list[AssetOverview]:
    rows: list[AssetOverview] = []
    for asset_id in asset_ids:
        asset_row = get_asset(db, asset_id)
        if asset_row is None:
            continue
        prices = [price_to_schema(row) for row in list_prices(db, asset_id)]
        news = [news_to_schema(row) for row in list_news(db, asset_id)]
        if len(prices) < 21:
            continue
        rows.append(build_overview(asset_to_schema(asset_row), prices, news))
    return rows


def compare_assets(db: Session, asset_ids: list[str]) -> CompareAssetsResponse:
    rows: list[CompareAssetRow] = []
    for asset_id in asset_ids:
        feature = get_latest_feature_snapshot(db, asset_id)
        forecasts = get_latest_forecasts(db, asset_id)
        forecast_1d = next((f for f in forecasts if f.horizon == "1d"), None)
        if feature is None:
            continue
        rows.append(
            CompareAssetRow(
                asset_id=asset_id,
                last_price=feature.last_price,
                trend_score=feature.trend_score,
                sentiment_score=feature.sentiment_score,
                divergence_score=feature.divergence_score,
                fragility_score=feature.fragility_score,
                regime=feature.regime_label,
                dominant_narrative=feature.dominant_narrative,
                forecast_direction_1d=forecast_1d.direction if forecast_1d else None,
                forecast_confidence_1d=forecast_1d.confidence if forecast_1d else None,
            )
        )
    return CompareAssetsResponse(asset_ids=asset_ids, rows=rows)
