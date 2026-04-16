from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ConfidenceContribution(BaseModel):
    name: str
    contribution: float


class ScenarioBlock(BaseModel):
    title: str
    summary: str
    drivers: List[str]


class ChangeItem(BaseModel):
    metric: str
    previous: str
    current: str
    delta: str
    interpretation: str


class PositionSizingResponse(BaseModel):
    suggested_size_label: str
    sizing_fraction: float
    rationale: str


class CrossAssetSignal(BaseModel):
    related_asset: str
    relationship: str
    confirmation: str
    interpretation: str


class RegimeMemoryItem(BaseModel):
    label: str
    similarity_score: float
    interpretation: str


class MacroPressureResponse(BaseModel):
    usd_pressure: float
    real_yield_pressure: float
    safe_haven_demand: float
    central_bank_buying: float
    inflation_hedge_support: float
    summary: str


class RelativeStrengthResponse(BaseModel):
    ratio_name: str
    value: float
    interpretation: str


class CompanyRiskStackResponse(BaseModel):
    valuation_pressure: float
    earnings_sensitivity: float
    regulation_risk: float
    competition_pressure: float
    product_cycle_strength: float
    summary: str


class DecisionSnapshotResponse(BaseModel):
    asset_id: str
    snapshot_at: datetime
    conviction_score: float
    risk_score: float
    timing_score: float
    setup_quality_score: float
    bullish_strength: float
    bearish_pressure: float
    net_thesis_edge: float
    action_label: str
    confidence_breakdown: List[ConfidenceContribution]
    scenario_base: ScenarioBlock
    scenario_bull: ScenarioBlock
    scenario_bear: ScenarioBlock
    change_summary: List[ChangeItem]
    position_sizing: PositionSizingResponse
    cross_asset_confirmation: List[CrossAssetSignal]
    regime_memory: List[RegimeMemoryItem]
    macro_pressure: Optional[MacroPressureResponse] = None
    relative_strength: Optional[RelativeStrengthResponse] = None
    company_risk_stack: Optional[CompanyRiskStackResponse] = None
