from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DailyAssetFeatureORM
from app.schemas.features import DailyAssetFeatureSnapshot


def insert_feature_snapshot(db: Session, snapshot: DailyAssetFeatureSnapshot) -> DailyAssetFeatureORM:
    row = DailyAssetFeatureORM(**snapshot.model_dump())
    db.add(row)
    db.flush()
    return row


def list_feature_history(db: Session, asset_id: str, limit: int = 90) -> list[DailyAssetFeatureORM]:
    stmt = (
        select(DailyAssetFeatureORM)
        .where(DailyAssetFeatureORM.asset_id == asset_id)
        .order_by(DailyAssetFeatureORM.snapshot_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


def get_latest_feature_snapshot(db: Session, asset_id: str) -> DailyAssetFeatureORM | None:
    stmt = (
        select(DailyAssetFeatureORM)
        .where(DailyAssetFeatureORM.asset_id == asset_id)
        .order_by(DailyAssetFeatureORM.snapshot_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def delete_feature_snapshot_for_timestamp(db: Session, asset_id: str, snapshot_at) -> None:
    db.execute(
        delete(DailyAssetFeatureORM).where(
            DailyAssetFeatureORM.asset_id == asset_id,
            DailyAssetFeatureORM.snapshot_at == snapshot_at,
        )
    )
