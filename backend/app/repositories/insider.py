from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InsiderTradeORM, ShortInterestORM


def list_insider_trades(db: Session, asset_id: str, limit: int = 20) -> list[InsiderTradeORM]:
    return list(db.scalars(
        select(InsiderTradeORM)
        .where(InsiderTradeORM.asset_id == asset_id)
        .order_by(InsiderTradeORM.transaction_date.desc())
        .limit(limit)
    ).all())


def get_short_interest_history(db: Session, asset_id: str, limit: int = 6) -> list[ShortInterestORM]:
    return list(db.scalars(
        select(ShortInterestORM)
        .where(ShortInterestORM.asset_id == asset_id)
        .order_by(ShortInterestORM.report_date.desc())
        .limit(limit)
    ).all())


def get_latest_short_interest(db: Session, asset_id: str) -> ShortInterestORM | None:
    return db.scalar(
        select(ShortInterestORM)
        .where(ShortInterestORM.asset_id == asset_id)
        .order_by(ShortInterestORM.report_date.desc())
        .limit(1)
    )


def upsert_insider_trade(db: Session, trade: InsiderTradeORM) -> InsiderTradeORM:
    existing = db.scalar(
        select(InsiderTradeORM).where(
            InsiderTradeORM.asset_id == trade.asset_id,
            InsiderTradeORM.transaction_date == trade.transaction_date,
            InsiderTradeORM.name == trade.name,
            InsiderTradeORM.transaction_code == trade.transaction_code,
            InsiderTradeORM.shares == trade.shares,
        )
    )
    if existing:
        return existing
    db.add(trade)
    db.flush()
    return trade


def upsert_short_interest(db: Session, si: ShortInterestORM) -> ShortInterestORM:
    existing = db.scalar(
        select(ShortInterestORM).where(
            ShortInterestORM.asset_id == si.asset_id,
            ShortInterestORM.report_date == si.report_date,
        )
    )
    if existing:
        existing.shares_short = si.shares_short
        existing.short_percent_float = si.short_percent_float
        existing.short_ratio = si.short_ratio
        db.flush()
        return existing
    db.add(si)
    db.flush()
    return si
