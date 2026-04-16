from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: int
    asset_id: str
    created_at: datetime
    alert_type: str
    severity: str
    title: str
    message: str
    status: str
    trigger_value: float
    threshold_value: float
    snapshot_json: str


class AlertRuleResponse(BaseModel):
    id: int
    rule_name: str
    is_enabled: bool
    alert_type: str
    asset_scope: str
    threshold_json: str
    severity: str
    cooldown_minutes: int


class AlertRuleCreate(BaseModel):
    rule_name: str
    is_enabled: bool = True
    alert_type: str
    asset_scope: str = "all"
    threshold_json: str
    severity: str = "medium"
    cooldown_minutes: int = 60
