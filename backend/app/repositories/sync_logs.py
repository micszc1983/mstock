from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SyncLogORM


def add_sync_log(
    db: Session,
    asset_id: str,
    sync_type: str,
    provider: str,
    inserted: int,
    skipped: int,
    status: str,
    detail: str,
) -> None:
    db.add(
        SyncLogORM(
            asset_id=asset_id,
            sync_type=sync_type,
            provider=provider,
            inserted=inserted,
            skipped=skipped,
            status=status,
            detail=detail,
            created_at=datetime.now(timezone.utc),
        )
    )


def list_sync_logs(db: Session, limit: int = 50) -> list[SyncLogORM]:
    return db.scalars(select(SyncLogORM).order_by(SyncLogORM.created_at.desc()).limit(limit)).all()
