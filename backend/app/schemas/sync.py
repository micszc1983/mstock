from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IngestPriceRequest(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class SyncResponse(BaseModel):
    asset_id: str
    provider: str
    inserted: int
    skipped: int
    detail: str


class SyncLogResponse(BaseModel):
    id: int
    asset_id: str
    sync_type: str
    provider: str
    inserted: int
    skipped: int
    status: str
    detail: str
    created_at: datetime
