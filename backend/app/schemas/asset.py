from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.common import AssetType


class Asset(BaseModel):
    id: str
    symbol: str
    name: str
    type: AssetType
    currency: str = "USD"           # waluta przechowywanych cen: "USD" | "PLN"
    sector: Optional[str] = None
    description: Optional[str] = None
    price_symbol: Optional[str] = None
    news_symbol: Optional[str] = None
    news_term: Optional[str] = None
    metal_price_fn: Optional[str] = None


class AssetCreate(BaseModel):
    id: str                          # np. "amzn" — lowercase, bez spacji
    symbol: str                      # np. "AMZN"
    name: str                        # np. "Amazon"
    type: AssetType
    currency: str = "USD"           # waluta przechowywanych cen: "USD" | "PLN"
    sector: Optional[str] = None
    description: Optional[str] = None
    # Konfiguracja providera
    price_symbol: Optional[str] = None      # symbol w Alpha Vantage, np. "AMZN"
    news_symbol: Optional[str] = None       # symbol w Finnhub (akcje), np. "AMZN"
    news_term: Optional[str] = None         # termin do wyszukiwania newsów, np. "Amazon"
    metal_price_fn: Optional[str] = None    # funkcja Alpha Vantage dla metali, np. "GOLD"


class PricePoint(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
