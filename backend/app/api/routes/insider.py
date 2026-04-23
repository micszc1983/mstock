from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset
from app.repositories.insider import (
    get_short_interest_history,
    list_insider_trades,
)
from app.schemas.insider import InsiderTrade, ShortInterest
from app.services.insider_service import sync_all_insider_data, sync_insider_data

router = APIRouter(tags=["insider"])


@router.get("/assets/{asset_id}/insider-trades", response_model=list[InsiderTrade])
def get_asset_insider_trades(
    asset_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[InsiderTrade]:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    rows = list_insider_trades(db, asset_id, limit=limit)
    return [InsiderTrade.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/short-interest", response_model=list[ShortInterest])
def get_asset_short_interest(
    asset_id: str,
    limit: int = 6,
    db: Session = Depends(get_db),
) -> list[ShortInterest]:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    rows = get_short_interest_history(db, asset_id, limit=limit)
    return [ShortInterest.model_validate(r) for r in rows]


@router.post("/assets/{asset_id}/sync/insider")
def sync_asset_insider(asset_id: str, db: Session = Depends(get_db)) -> dict:
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    result = sync_insider_data(db, asset_row)
    return {"asset_id": asset_id, **result}


@router.post("/sync/insider")
def sync_insider_all(db: Session = Depends(get_db)) -> dict:
    def _run() -> None:
        sync_all_insider_data(db)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"started": True, "message": "Synchronizacja insider data uruchomiona w tle."}
