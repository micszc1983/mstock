from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel


class NewsNarrativePredictionResponse(BaseModel):
    news_id: str
    model_name: str
    narrative_label: str
    score: float
    confidence: float


class NewsNLPResponse(BaseModel):
    news_id: str
    model_name: str
    processed_at: datetime
    sentiment_score: float
    sentiment_label: str
    sentiment_confidence: float
    relevance_score: float
    raw_output_json: str
    narratives: List[NewsNarrativePredictionResponse]
