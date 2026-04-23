from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class EarningsCallAnalysis(BaseModel):
    id: int
    earnings_id: int
    asset_id: str
    analyzed_at: datetime
    tone_score: int                   # 1–5
    guidance_change: str              # raised/lowered/maintained/none
    key_themes: list[str]
    risk_factors: list[str]
    key_quote: Optional[str]
    llm_sentiment_score: float        # -100 do +100
    summary: str
    model_used: str
    news_articles_used: int

    model_config = {"from_attributes": True}

    @field_validator("key_themes", "risk_factors", mode="before")
    @classmethod
    def _parse_json(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v
