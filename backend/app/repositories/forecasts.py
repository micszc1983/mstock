from __future__ import annotations

from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from app.db.models import ForecastORM
from app.schemas.features import ForecastResponse


def insert_forecast(db: Session, forecast: ForecastResponse) -> ForecastORM:
    row = ForecastORM(**forecast.model_dump())
    db.add(row)
    db.flush()
    return row


def list_forecasts(db: Session, asset_id: str, horizon: str | None = None, limit: int = 30) -> list[ForecastORM]:
    stmt = select(ForecastORM).where(ForecastORM.asset_id == asset_id)
    if horizon:
        stmt = stmt.where(ForecastORM.horizon == horizon)
    stmt = stmt.order_by(ForecastORM.generated_at.desc()).limit(limit)
    return db.scalars(stmt).all()


def get_latest_forecasts(db: Session, asset_id: str) -> list[ForecastORM]:
    latest_ts = db.scalar(
        select(ForecastORM.generated_at)
        .where(ForecastORM.asset_id == asset_id)
        .order_by(ForecastORM.generated_at.desc())
        .limit(1)
    )
    if latest_ts is None:
        return []

    stmt = (
        select(ForecastORM)
        .where(ForecastORM.asset_id == asset_id, ForecastORM.generated_at == latest_ts)
        .order_by(ForecastORM.horizon.asc())
    )
    return db.scalars(stmt).all()


def list_forecast_history(
    db: Session,
    asset_id: str,
    horizon: str | None = None,
    limit: int = 100,
) -> list[ForecastORM]:
    stmt = select(ForecastORM).where(ForecastORM.asset_id == asset_id)
    if horizon:
        stmt = stmt.where(ForecastORM.horizon == horizon)
    stmt = stmt.order_by(ForecastORM.generated_at.desc(), ForecastORM.horizon.asc()).limit(limit)
    return db.scalars(stmt).all()


def delete_forecast_for_timestamp(db: Session, asset_id: str, generated_at) -> None:
    db.execute(
        delete(ForecastORM).where(
            ForecastORM.asset_id == asset_id,
            func.date(ForecastORM.generated_at) == func.date(generated_at),
        )
    )
