from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InsiderTrade(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: str
    transaction_date: date
    filing_date: Optional[date] = None
    name: str
    transaction_code: str
    transaction_type: str
    shares: Optional[float] = None
    price: Optional[float] = None
    value: Optional[float] = None
    source: str
    created_at: datetime


class ShortInterest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: str
    report_date: date
    shares_short: Optional[float] = None
    short_percent_float: Optional[float] = None
    short_ratio: Optional[float] = None
    created_at: datetime
