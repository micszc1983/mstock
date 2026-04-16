from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.notifications import (
    create_notification_channel,
    get_notification_channel,
    list_notification_channels,
    list_notification_events,
)
from app.schemas.notifications import (
    NotificationChannelCreate,
    NotificationChannelResponse,
    NotificationEventResponse,
)
from app.services.notification_service import send_email_notification, send_whatsapp_notification

router = APIRouter(tags=["notifications"])


@router.post("/notification-channels", response_model=NotificationChannelResponse)
def create_channel(payload: NotificationChannelCreate, db: Session = Depends(get_db)) -> NotificationChannelResponse:
    row = create_notification_channel(db, payload.channel_type, payload.target, payload.label, payload.is_enabled)
    db.commit()
    db.refresh(row)
    return NotificationChannelResponse(
        id=row.id,
        channel_type=row.channel_type,
        target=row.target,
        label=row.label,
        is_enabled=row.is_enabled,
        created_at=row.created_at,
    )


@router.get("/notification-channels", response_model=list[NotificationChannelResponse])
def get_channels(db: Session = Depends(get_db)) -> list[NotificationChannelResponse]:
    return [
        NotificationChannelResponse(
            id=row.id,
            channel_type=row.channel_type,
            target=row.target,
            label=row.label,
            is_enabled=row.is_enabled,
            created_at=row.created_at,
        )
        for row in list_notification_channels(db)
    ]


@router.get("/notification-events", response_model=list[NotificationEventResponse])
def get_events(limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[NotificationEventResponse]:
    return [
        NotificationEventResponse(
            id=row.id,
            channel_id=row.channel_id,
            asset_id=row.asset_id,
            event_type=row.event_type,
            status=row.status,
            message=row.message,
            created_at=row.created_at,
        )
        for row in list_notification_events(db, limit=limit)
    ]


@router.post("/notifications/email/{channel_id}")
def notify_email(channel_id: int, subject: str = Query(...), message: str = Query(...), asset_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    if get_notification_channel(db, channel_id) is None:
        raise HTTPException(status_code=404, detail="Unknown notification channel")
    return send_email_notification(db, channel_id, subject, message, asset_id=asset_id)


@router.post("/notifications/whatsapp/{channel_id}")
def notify_whatsapp(channel_id: int, message: str = Query(...), asset_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    if get_notification_channel(db, channel_id) is None:
        raise HTTPException(status_code=404, detail="Unknown notification channel")
    return send_whatsapp_notification(db, channel_id, message, asset_id=asset_id)
