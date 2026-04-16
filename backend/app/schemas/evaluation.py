from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class WalkForwardBacktestResponse(BaseModel):
    model_run_id: int
    created_at: datetime
    result_json: str


class StrategyComparisonResponse(BaseModel):
    asset_id: str
    heuristic_accuracy_5d: float
    ml_accuracy_5d: float
    heuristic_avg_return_5d: float
    ml_avg_return_5d: float
    better_mode: str
    sample_size: int
