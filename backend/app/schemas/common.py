from __future__ import annotations

from enum import Enum


class AssetType(str, Enum):
    STOCK = "stock"
    METAL = "metal"


class RegimeLabel(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    EARNINGS_DRIVEN = "earnings_driven"
    MACRO_DRIVEN = "macro_driven"
    RANGE_BOUND = "range_bound"
    SAFE_HAVEN = "safe_haven"


class NarrativeLabel(str, Enum):
    AI_GROWTH = "ai_growth"
    MARGIN_PRESSURE = "margin_pressure"
    DEMAND_STRENGTH = "demand_strength"
    DEMAND_SLOWDOWN = "demand_slowdown"
    REGULATION_RISK = "regulation_risk"
    VALUATION_STRETCH = "valuation_stretch"
    SAFE_HAVEN = "safe_haven"
    RATES_PRESSURE = "rates_pressure"
    DOLLAR_PRESSURE = "dollar_pressure"
    CENTRAL_BANK_BUYING = "central_bank_buying"
    INDUSTRIAL_DEMAND = "industrial_demand"
    SUPPLY_DISRUPTION = "supply_disruption"
