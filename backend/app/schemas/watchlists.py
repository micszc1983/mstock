from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class WatchlistCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: bool = False


class WatchlistResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_default: bool
    created_at: datetime
    assets: List[str] = []


class PreferenceUpsert(BaseModel):
    preference_key: str
    preference_value: str


class PreferenceResponse(BaseModel):
    id: int
    preference_key: str
    preference_value: str
    updated_at: datetime
