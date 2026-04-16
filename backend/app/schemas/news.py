from __future__ import annotations

from datetime import datetime
from typing import Dict

from pydantic import BaseModel, Field

from app.schemas.common import NarrativeLabel


class NewsItem(BaseModel):
    id: str
    asset_id: str
    published_at: datetime
    source: str
    title: str
    body: str
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    impact_score: float = Field(ge=0.0, le=1.0)
    narratives: Dict[NarrativeLabel, float]


class IngestNewsRequest(BaseModel):
    id: str
    published_at: datetime
    source: str
    title: str
    body: str
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    impact_score: float = Field(ge=0.0, le=1.0)
    narratives: Dict[NarrativeLabel, float]


class NarrativePoint(BaseModel):
    date: datetime
    narrative_scores: Dict[str, float]
