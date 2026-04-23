from __future__ import annotations

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset
from app.repositories.earnings import get_latest_earnings, list_earnings_for_asset
from app.repositories.earnings_analysis import get_analysis_for_earnings, list_analyses_for_asset
from app.schemas.earnings import EarningsCalendarResponse, EarningsRecord
from app.schemas.earnings_analysis import EarningsCallAnalysis
from app.services.earnings_service import build_earnings_calendar, sync_all_earnings, sync_earnings_for_asset

router = APIRouter(tags=["earnings"])


@router.get("/earnings/calendar", response_model=EarningsCalendarResponse)
def get_earnings_calendar(db: Session = Depends(get_db)) -> EarningsCalendarResponse:
    """Kalendarz wynikowy: nadchodzące raporty + ostatnie 8 tygodni z zaskoczeniem."""
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


@router.get("/assets/{asset_id}/earnings/analyses", response_model=list[EarningsCallAnalysis])
def get_earnings_analyses(
    asset_id: str,
    limit: int = 8,
    db: Session = Depends(get_db),
) -> list[EarningsCallAnalysis]:
    """Lista analiz LLM wyników kwartalnych dla aktywa."""
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    rows = list_analyses_for_asset(db, asset_id, limit=limit)
    return [EarningsCallAnalysis.model_validate(r) for r in rows]


@router.post("/assets/{asset_id}/earnings/latest/analyze", response_model=Optional[EarningsCallAnalysis])
def analyze_latest_earnings(asset_id: str, db: Session = Depends(get_db)):
    """Uruchamia analizę LLM dla najnowszego raportu wynikowego aktywa."""
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    from app.services.earnings_llm import analyze_earnings
    earnings = get_latest_earnings(db, asset_id)
    if earnings is None:
        raise HTTPException(status_code=404, detail="Brak danych wynikowych dla tego aktywa.")
    result = analyze_earnings(db, earnings, asset_row)
    if result is None:
        raise HTTPException(status_code=503, detail="Analiza LLM niedostępna (brak klucza API lub błąd).")
    return EarningsCallAnalysis.model_validate(result)


@router.post("/assets/{asset_id}/earnings/{earnings_id}/analyze", response_model=Optional[EarningsCallAnalysis])
def analyze_earnings_record(asset_id: str, earnings_id: int, db: Session = Depends(get_db)):
    """Uruchamia analizę LLM dla konkretnego rekordu wynikowego."""
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    from sqlalchemy import select
    from app.db.models import EarningsORM
    earnings = db.scalar(select(EarningsORM).where(EarningsORM.id == earnings_id, EarningsORM.asset_id == asset_id))
    if earnings is None:
        raise HTTPException(status_code=404, detail=f"Earnings record {earnings_id} not found.")
    from app.services.earnings_llm import analyze_earnings
    result = analyze_earnings(db, earnings, asset_row)
    if result is None:
        raise HTTPException(status_code=503, detail="Analiza LLM niedostępna (brak klucza API lub błąd).")
    return EarningsCallAnalysis.model_validate(result)


@router.post("/sync/earnings")
def sync_earnings(db: Session = Depends(get_db)) -> dict:
    """Wymuś synchronizację danych wynikowych dla wszystkich aktywów (działa w tle)."""
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
