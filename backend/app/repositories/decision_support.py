from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DecisionSnapshotORM


def insert_decision_snapshot(db: Session, **kwargs) -> DecisionSnapshotORM:
    row = DecisionSnapshotORM(**kwargs)
    db.add(row)
    db.flush()
    return row


def delete_decision_snapshot_for_timestamp(db: Session, asset_id: str, snapshot_at) -> None:
    db.execute(
        delete(DecisionSnapshotORM).where(
            DecisionSnapshotORM.asset_id == asset_id,
            DecisionSnapshotORM.snapshot_at == snapshot_at,
        )
    )


def get_latest_decision_snapshot(db: Session, asset_id: str) -> DecisionSnapshotORM | None:
    stmt = (
        select(DecisionSnapshotORM)
        .where(DecisionSnapshotORM.asset_id == asset_id)
        .order_by(DecisionSnapshotORM.snapshot_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def list_decision_history(db: Session, asset_id: str, limit: int = 50) -> list[DecisionSnapshotORM]:
    stmt = (
        select(DecisionSnapshotORM)
        .where(DecisionSnapshotORM.asset_id == asset_id)
        .order_by(DecisionSnapshotORM.snapshot_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()
