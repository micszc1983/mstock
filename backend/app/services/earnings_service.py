"""
earnings_service.py

Synchronizuje i agreguje dane wynikowe (EPS, revenue, surprise) dla aktywów.
Źródła: Finnhub (historyczne) + yfinance (nadchodzące daty).

Tylko dla aktywów typu 'stock'. Metale i ETF bez EPS → pomijane.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import AssetORM
from app.repositories.earnings import (
    upsert_earnings,
    list_earnings_for_asset,
    list_upcoming_earnings,
    list_recent_earnings,
)
from app.repositories.assets import list_assets, get_asset
from app.schemas.earnings import EarningsCalendarEntry, EarningsCalendarResponse


# ETF-y które mają price_symbol ale nie mają sensownych EPS
_ETF_SYMBOLS = {"QQQ", "SOXX", "BOTZ", "AIQ", "SPY", "IWM", "GLD", "SLV"}


def _should_sync_earnings(asset_row: AssetORM) -> bool:
    """Tylko akcje z symbolem — nie metale, nie ETFy bez EPS."""
    if asset_row.type == "metal":
        return False
    if (asset_row.sector or "").upper().startswith("ETF"):
        return False
    symbol = (asset_row.price_symbol or asset_row.symbol or "").upper()
    if symbol in _ETF_SYMBOLS:
        return False
    return True


def sync_earnings_for_asset(db: Session, asset_row: AssetORM) -> int:
    """
    Pobiera i zapisuje dane wynikowe dla jednego aktywa.
    Zwraca liczbę upsertowanych rekordów.
    """
    if not _should_sync_earnings(asset_row):
        return 0

    symbol = asset_row.price_symbol or asset_row.symbol
    count = 0

    # ── Historyczne wyniki z Finnhub ─────────────────────────────────────────
    from app.services.providers import fetch_earnings_from_finnhub
    hist = fetch_earnings_from_finnhub(symbol)
    for rec in hist:
        upsert_earnings(db, asset_row.id, **rec)
        count += 1

    # ── Nadchodzące daty z yfinance ──────────────────────────────────────────
    from app.services.providers import fetch_upcoming_earnings_from_yfinance
    upcoming = fetch_upcoming_earnings_from_yfinance(symbol)
    for rec in upcoming:
        # Nie nadpisuj istniejącego historycznego rekordu dla tej samej daty
        existing_hist = next(
            (h for h in hist if h["report_date"] == rec["report_date"]), None
        )
        if existing_hist is None:
            upsert_earnings(db, asset_row.id, **rec)
            count += 1

    if count > 0:
        db.commit()
    return count


def sync_all_earnings(db: Session) -> dict[str, int]:
    """Synchronizuje dane wynikowe dla wszystkich aktywów. Zwraca {asset_id: count}."""
    results: dict[str, int] = {}
    for asset_row in list_assets(db):
        n = sync_earnings_for_asset(db, asset_row)
        if n > 0:
            results[asset_row.id] = n
            print(f"[earnings] {asset_row.id}: +{n} rekordów")
    return results


def build_earnings_calendar(db: Session) -> EarningsCalendarResponse:
    """Buduje widok kalendarza wynikowego: nadchodzące + ostatnie 8 tygodni."""
    from app.repositories.assets import get_asset as _get

    def _to_entry(row, asset_id: str) -> Optional[EarningsCalendarEntry]:
        asset = _get(db, asset_id)
        if asset is None:
            return None
        return EarningsCalendarEntry(
            asset_id=asset_id,
            symbol=asset.symbol,
            name=asset.name,
            report_date=row.report_date,
            fiscal_period=row.fiscal_period,
            eps_estimate=row.eps_estimate,
            eps_actual=row.eps_actual,
            eps_surprise_pct=row.eps_surprise_pct,
            surprise_label=row.surprise_label,
            is_upcoming=row.is_upcoming,
        )

    upcoming_rows = list_upcoming_earnings(db, days_ahead=90)
    recent_rows   = list_recent_earnings(db, days_back=56)

    upcoming = [e for row in upcoming_rows if (e := _to_entry(row, row.asset_id)) is not None]
    recent   = [e for row in recent_rows   if (e := _to_entry(row, row.asset_id)) is not None]

    return EarningsCalendarResponse(upcoming=upcoming, recent=recent)


def get_latest_earnings_surprise(db: Session, asset_id: str) -> Optional[float]:
    """
    Zwraca eps_surprise_pct ostatniego raportu (< 90 dni temu) lub None.
    Używane przez recommendation_engine jako sygnał fundamentalny.
    """
    from app.repositories.earnings import get_latest_earnings
    row = get_latest_earnings(db, asset_id)
    if row is None:
        return None
    # Ignoruj starsze niż 90 dni (za stare żeby wpływać na bieżącą rekomendację)
    if (date.today() - row.report_date).days > 90:
        return None
    return row.eps_surprise_pct
