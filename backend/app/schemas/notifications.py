from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class NotificationChannelCreate(BaseModel):
    channel_type: str
    target: str
    label: str
    is_enabled: bool = True


class NotificationChannelResponse(BaseModel):
    id: int
    channel_type: str
    target: str
    label: str
    is_enabled: bool
    created_at: datetime


class NotificationEventResponse(BaseModel):
    id: int
    channel_id: int
    asset_id: str | None = None
    event_type: str
    status: str
    message: str
    created_at: datetime
