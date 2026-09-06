from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AssetORM
from app.mappers import asset_to_schema, price_to_schema
from app.repositories.prices import list_prices
from app.repositories.theses import delete_thesis_for_timestamp, insert_thesis
from app.schemas.thesis import ThesisResponse
from app.services.analytics import make_thesis
from app.services.market_calendar import market_session_close, market_session_date
from app.services.news_features import list_news_for_analysis


def persist_thesis_snapshot(db: Session, asset_row: AssetORM, snapshot_at) -> ThesisResponse | None:
    asset = asset_to_schema(asset_row)
    prices = [price_to_schema(row) for row in list_prices(db, asset.id)]
    price_symbol = asset_row.price_symbol or asset.symbol
    session_day = market_session_date(price_symbol, snapshot_at)
    news = list_news_for_analysis(
        db,
        asset.id,
        as_of=market_session_close(price_symbol, session_day),
    )
    if not prices:
        return None

    thesis = make_thesis(asset, prices, news)
    thesis.generated_at = snapshot_at
    delete_thesis_for_timestamp(db, asset.id, snapshot_at)
    insert_thesis(db, thesis, source_snapshot_at=snapshot_at)
    db.commit()
    return thesis
