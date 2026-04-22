from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class EarningsRecord(BaseModel):
    id: int
    asset_id: str
    report_date: date
    fiscal_period: Optional[str] = None       # "2025Q1"
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    eps_surprise_pct: Optional[float] = None  # (actual-est)/|est|*100
    surprise_label: Optional[str] = None      # "BEAT" | "MISS" | "MEET"
    is_upcoming: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EarningsCalendarEntry(BaseModel):
    """Pozycja w kalendarzu wynikowym (wiele aktywów, jeden widok)."""
    asset_id: str
    symbol: str
    name: str
    report_date: date
    fiscal_period: Optional[str] = None
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    eps_surprise_pct: Optional[float] = None
    surprise_label: Optional[str] = None
    is_upcoming: bool


class EarningsCalendarResponse(BaseModel):
    upcoming: list[EarningsCalendarEntry]    # posortowane rosnąco po dacie
    recent: list[EarningsCalendarEntry]      # ostatnie 8 tygodni, malejąco
