from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SyncLogORM
from app.utils.sanitization import redact_sensitive_text


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
            detail=redact_sensitive_text(detail),
            created_at=datetime.now(timezone.utc),
        )
    )


def list_sync_logs(db: Session, limit: int = 50) -> list[SyncLogORM]:
    return db.scalars(select(SyncLogORM).order_by(SyncLogORM.created_at.desc()).limit(limit)).all()


def redact_existing_sync_log_secrets(db: Session, secrets: tuple[str, ...] = ()) -> int:
    """Idempotentnie czyści stare logi utworzone przed wprowadzeniem redakcji."""
    changed = 0
    for row in db.scalars(select(SyncLogORM)).all():
        safe_detail = redact_sensitive_text(row.detail, secrets)
        if safe_detail != row.detail:
            row.detail = safe_detail
            changed += 1
    return changed
