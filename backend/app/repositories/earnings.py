from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.models import EarningsORM


def upsert_earnings(db: Session, asset_id: str, report_date: date, **fields) -> EarningsORM:
    """Wstaw lub zaktualizuj rekord wyników dla danego aktywa i daty."""
    row = db.scalar(
        select(EarningsORM)
        .where(EarningsORM.asset_id == asset_id, EarningsORM.report_date == report_date)
    )
    if row is None:
        row = EarningsORM(asset_id=asset_id, report_date=report_date, **fields)
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def list_earnings_for_asset(
    db: Session, asset_id: str, limit: int = 12
) -> list[EarningsORM]:
    stmt = (
        select(EarningsORM)
        .where(EarningsORM.asset_id == asset_id)
        .order_by(EarningsORM.report_date.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


def get_latest_earnings(db: Session, asset_id: str) -> EarningsORM | None:
    """Najnowszy *historyczny* wynik (eps_actual nie null)."""
    return db.scalar(
        select(EarningsORM)
        .where(EarningsORM.asset_id == asset_id, EarningsORM.eps_actual.isnot(None))
        .order_by(EarningsORM.report_date.desc())
        .limit(1)
    )


def list_upcoming_earnings(db: Session, days_ahead: int = 60) -> list[EarningsORM]:
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    stmt = (
        select(EarningsORM)
        .where(EarningsORM.is_upcoming == True, EarningsORM.report_date >= today,  # noqa: E712
               EarningsORM.report_date <= cutoff)
        .order_by(EarningsORM.report_date.asc())
    )
    return db.scalars(stmt).all()


def list_recent_earnings(db: Session, days_back: int = 56) -> list[EarningsORM]:
    cutoff = date.today() - timedelta(days=days_back)
    stmt = (
        select(EarningsORM)
        .where(EarningsORM.eps_actual.isnot(None), EarningsORM.report_date >= cutoff)
        .order_by(EarningsORM.report_date.desc())
    )
    return db.scalars(stmt).all()
