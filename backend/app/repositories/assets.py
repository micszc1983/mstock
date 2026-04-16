from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AssetORM


def list_assets(db: Session) -> list[AssetORM]:
    return db.scalars(select(AssetORM).order_by(AssetORM.name.asc())).all()


def get_asset(db: Session, asset_id: str) -> AssetORM | None:
    return db.get(AssetORM, asset_id)


def create_asset(
    db,
    asset_id: str,
    symbol: str,
    name: str,
    asset_type: str,
    currency: str = "USD",
    sector: str | None = None,
    description: str | None = None,
    price_symbol: str | None = None,
    news_symbol: str | None = None,
    news_term: str | None = None,
    metal_price_fn: str | None = None,
) -> "AssetORM":
    row = AssetORM(
        id=asset_id,
        symbol=symbol,
        name=name,
        type=asset_type,
        currency=currency,
        sector=sector,
        description=description,
        price_symbol=price_symbol,
        news_symbol=news_symbol,
        news_term=news_term or name,
        metal_price_fn=metal_price_fn,
    )
    db.add(row)
    db.flush()
    return row


def delete_asset_cascade(db, asset_id: str) -> None:
    """Usuwa aktywo i wszystkie powiązane dane (ceny, newsy, features, forecasts, tezy, ML itp.)."""
    from sqlalchemy import delete as _del
    from app.db.models import (
        DailyAssetFeatureORM, ForecastORM, ThesisORM, ThesisOutcomeORM,
        AlertORM, MLTrainingRowORM, MLPredictionORM, HeuristicVsMLComparisonORM,
        DecisionSnapshotORM, SyncLogORM, NewsNLPRunORM, NewsNarrativePredictionORM,
        WatchlistItemORM, NotificationEventORM,
    )
    # Kolejność usuwania: najpierw tabele zależne, na końcu asset
    for model, col in [
        (ThesisOutcomeORM,          ThesisOutcomeORM.asset_id),
        (MLPredictionORM,           MLPredictionORM.asset_id),
        (MLTrainingRowORM,          MLTrainingRowORM.asset_id),
        (HeuristicVsMLComparisonORM,HeuristicVsMLComparisonORM.asset_id),
        (DecisionSnapshotORM,       DecisionSnapshotORM.asset_id),
        (AlertORM,                  AlertORM.asset_id),
        (ForecastORM,               ForecastORM.asset_id),
        (DailyAssetFeatureORM,      DailyAssetFeatureORM.asset_id),
        (WatchlistItemORM,          WatchlistItemORM.asset_id),
        (NotificationEventORM,      NotificationEventORM.asset_id),
    ]:
        db.execute(_del(model).where(col == asset_id))

    # SyncLog (asset_id to String bez FK)
    db.execute(_del(SyncLogORM).where(SyncLogORM.asset_id == asset_id))

    # Tezy — najpierw usuń NLP runs powiązane z newsami tego aktywa
    from app.db.models import NewsItemORM
    news_ids = db.scalars(select(NewsItemORM.id).where(NewsItemORM.asset_id == asset_id)).all()
    if news_ids:
        db.execute(_del(NewsNLPRunORM).where(NewsNLPRunORM.news_id.in_(news_ids)))
        db.execute(_del(NewsNarrativePredictionORM).where(NewsNarrativePredictionORM.news_id.in_(news_ids)))

    # Tezy (PricePoints i NewsItems mają cascade przez relationship)
    db.execute(_del(ThesisORM).where(ThesisORM.asset_id == asset_id))

    # Asset (kaskada w SQLAlchemy usunie PricePoints i NewsItems przez relationship)
    asset = db.get(AssetORM, asset_id)
    if asset:
        db.delete(asset)
