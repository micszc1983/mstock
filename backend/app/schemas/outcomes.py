from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ThesisOutcomeResponse(BaseModel):
    thesis_id: int
    asset_id: str
    evaluated_at: datetime
    horizon: str
    base_price: float
    realized_price: float
    realized_return_pct: float
    was_directionally_correct: bool
    outcome_label: str
