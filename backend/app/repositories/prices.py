from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PricePointORM
from app.schemas.asset import PricePoint


def list_prices(db: Session, asset_id: str, limit: int | None = None) -> list[PricePointORM]:
    stmt = select(PricePointORM).where(PricePointORM.asset_id == asset_id).order_by(PricePointORM.timestamp.asc())
    rows = db.scalars(stmt).all()
    return rows[-limit:] if limit is not None else rows


def upsert_price_point(db: Session, asset_id: str, point: PricePoint) -> bool:
    from sqlalchemy import func, cast
    import sqlalchemy as sa

    # Dopasuj po dacie (nie po dokładnym timestamp) — Alpaca używa 04:00:00Z, seed 00:00:00Z
    point_date = point.timestamp.date() if hasattr(point.timestamp, "date") else point.timestamp

    existing = db.scalar(
        select(PricePointORM).where(
            PricePointORM.asset_id == asset_id,
            func.date(PricePointORM.timestamp) == point_date,
        )
    )
    if existing:
        existing.timestamp = point.timestamp  # zaktualizuj timestamp na nowszy (np. Alpaca)
        existing.open   = point.open
        existing.high   = point.high
        existing.low    = point.low
        existing.close  = point.close
        existing.volume = point.volume
        return False

    db.add(PricePointORM(
        asset_id=asset_id,
        timestamp=point.timestamp,
        open=point.open,
        high=point.high,
        low=point.low,
        close=point.close,
        volume=point.volume,
    ))
    return True
