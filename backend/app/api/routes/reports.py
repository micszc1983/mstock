from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.repositories.watchlists import get_watchlist
from app.schemas.reports import ReportResponse
from app.services.report_service import generate_asset_daily_report, generate_watchlist_daily_report

router = APIRouter(tags=["reports"])


@router.post("/reports/daily/asset/{asset_id}", response_model=ReportResponse)
def generate_asset_report(asset_id: str, db: Session = Depends(get_db)) -> ReportResponse:
    file_path, file_name = generate_asset_daily_report(db, asset_id)
    return ReportResponse(
        asset_id=asset_id,
        watchlist_id=None,
        report_type="daily_asset",
        generated_at=datetime.now(timezone.utc),
        file_path=file_path,
        file_name=file_name,
    )


@router.post("/reports/daily/watchlist/{watchlist_id}", response_model=ReportResponse)
def generate_watchlist_report(watchlist_id: int, db: Session = Depends(get_db)) -> ReportResponse:
    if get_watchlist(db, watchlist_id) is None:
        raise HTTPException(status_code=404, detail="Unknown watchlist")
    file_path, file_name = generate_watchlist_daily_report(db, watchlist_id)
    return ReportResponse(
        asset_id=None,
        watchlist_id=watchlist_id,
        report_type="daily_watchlist",
        generated_at=datetime.now(timezone.utc),
        file_path=file_path,
        file_name=file_name,
    )


@router.get("/reports/download/{file_name}")
def download_report(file_name: str):
    reports_dir = Path(settings.reports_dir).resolve()
    safe_name = Path(file_name).name
    file_path = (reports_dir / safe_name).resolve()

    if reports_dir not in file_path.parents and file_path != reports_dir / safe_name:
        raise HTTPException(status_code=400, detail="Invalid report path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(str(file_path), filename=safe_name, media_type="application/pdf")
