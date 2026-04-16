from __future__ import annotations
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.models import EnsembleRecordORM
from app.utils.datetime import now_utc


def insert_ensemble_record(db: Session, **kwargs) -> EnsembleRecordORM:
    row = EnsembleRecordORM(created_at=now_utc(), **kwargs)
    db.add(row)
    db.flush()
    return row


def list_ensemble_records(db: Session, asset_id: str, limit: int = 200) -> list[EnsembleRecordORM]:
    return db.scalars(
        select(EnsembleRecordORM)
        .where(EnsembleRecordORM.asset_id == asset_id)
        .order_by(EnsembleRecordORM.created_at.desc())
        .limit(limit)
    ).all()


def list_all_ensemble_records(db: Session, limit: int = 500) -> list[EnsembleRecordORM]:
    return db.scalars(
        select(EnsembleRecordORM)
        .order_by(EnsembleRecordORM.created_at.desc())
        .limit(limit)
    ).all()


def get_pending_outcome_records(db: Session, limit: int = 500) -> list[EnsembleRecordORM]:
    """Rekordy bez outcome — czekają na wypełnienie przez outcome evaluator."""
    return db.scalars(
        select(EnsembleRecordORM)
        .where(EnsembleRecordORM.actual_return_5d.is_(None))
        .order_by(EnsembleRecordORM.created_at.asc())
        .limit(limit)
    ).all()
