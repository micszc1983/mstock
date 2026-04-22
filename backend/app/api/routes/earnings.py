from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset
from app.repositories.earnings import list_earnings_for_asset
from app.schemas.earnings import EarningsCalendarResponse, EarningsRecord
from app.services.earnings_service import build_earnings_calendar, sync_all_earnings, sync_earnings_for_asset

router = APIRouter(tags=["earnings"])


@router.get("/earnings/calendar", response_model=EarningsCalendarResponse)
def get_earnings_calendar(db: Session = Depends(get_db)) -> EarningsCalendarResponse:
    """Kalendarz wynikowy: nadchodzące raporty + ostatnie 8 tygodni z zaskoczenieam."""
    return build_earnings_calendar(db)


@router.get("/assets/{asset_id}/earnings", response_model=list[EarningsRecord])
def get_asset_earnings(
    asset_id: str,
    limit: int = 8,
    db: Session = Depends(get_db),
) -> list[EarningsRecord]:
    """Historyczne wyniki kwartalne dla jednego aktywa (EPS est vs actual, surprise)."""
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    rows = list_earnings_for_asset(db, asset_id, limit=limit)
    return [EarningsRecord.model_validate(r) for r in rows]


@router.post("/sync/earnings")
def sync_earnings(db: Session = Depends(get_db)) -> dict:
    """Wymuś synchronizację danych wynikowych dla wszystkich aktywów (działa w tle)."""
    import threading
    def _run():
        sync_all_earnings(db)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"started": True, "message": "Synchronizacja wyników uruchomiona w tle."}


@router.post("/assets/{asset_id}/sync/earnings")
def sync_asset_earnings(asset_id: str, db: Session = Depends(get_db)) -> dict:
    """Wymuś synchronizację danych wynikowych dla jednego aktywa."""
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    n = sync_earnings_for_asset(db, asset_row)
    return {"asset_id": asset_id, "synced_records": n}
