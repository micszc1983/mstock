from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import decision_snapshot_to_schema
from app.repositories.assets import get_asset
from app.repositories.decision_support import get_latest_decision_snapshot, list_decision_history
from app.schemas.decision_support import DecisionSnapshotResponse
from app.services.decision_support import persist_decision_snapshot

router = APIRouter(tags=["decision_support"])


@router.post("/assets/{asset_id}/decision/rebuild", response_model=DecisionSnapshotResponse)
def rebuild_decision(asset_id: str, db: Session = Depends(get_db)) -> DecisionSnapshotResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    snapshot = persist_decision_snapshot(db, asset_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Could not build decision snapshot for {asset_id}")
    return snapshot


@router.get("/assets/{asset_id}/decision/latest", response_model=DecisionSnapshotResponse)
def get_latest_decision(asset_id: str, db: Session = Depends(get_db)) -> DecisionSnapshotResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    row = get_latest_decision_snapshot(db, asset_id)
    if row is None:
        snapshot = persist_decision_snapshot(db, asset_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"No decision snapshot for {asset_id}")
        return snapshot
    return decision_snapshot_to_schema(row)


@router.get("/assets/{asset_id}/decision/history", response_model=list[DecisionSnapshotResponse])
def get_decision_history(asset_id: str, limit: int = Query(default=20, ge=1, le=365), db: Session = Depends(get_db)) -> list[DecisionSnapshotResponse]:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    rows = list_decision_history(db, asset_id, limit=limit)
    return [decision_snapshot_to_schema(row) for row in rows]
