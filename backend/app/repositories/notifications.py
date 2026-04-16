from __future__ import annotations

from app.utils.datetime import now_utc

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NotificationChannelORM, NotificationEventORM


def create_notification_channel(db: Session, channel_type: str, target: str, label: str, is_enabled: bool) -> NotificationChannelORM:
    row = NotificationChannelORM(
        channel_type=channel_type,
        target=target,
        label=label,
        is_enabled=is_enabled,
        created_at=now_utc(),
    )
    db.add(row)
    db.flush()
    return row


def list_notification_channels(db: Session) -> list[NotificationChannelORM]:
    return db.scalars(select(NotificationChannelORM).order_by(NotificationChannelORM.created_at.desc())).all()


def get_notification_channel(db: Session, channel_id: int) -> NotificationChannelORM | None:
    return db.get(NotificationChannelORM, channel_id)


def create_notification_event(
    db: Session,
    channel_id: int,
    asset_id: str | None,
    event_type: str,
    status: str,
    message: str,
) -> NotificationEventORM:
    row = NotificationEventORM(
        channel_id=channel_id,
        asset_id=asset_id,
        event_type=event_type,
        status=status,
        message=message,
        created_at=now_utc(),
    )
    db.add(row)
    db.flush()
    return row


def list_notification_events(db: Session, limit: int = 100) -> list[NotificationEventORM]:
    return db.scalars(select(NotificationEventORM).order_by(NotificationEventORM.created_at.desc()).limit(limit)).all()
