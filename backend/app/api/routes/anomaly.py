from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import AssetORM
from app.services.anomaly_service import get_latest, get_history, train_and_score

router = APIRouter(prefix="/assets", tags=["anomaly"])


def _asset_or_404(db: Session, asset_id: str) -> AssetORM:
    from sqlalchemy import select
    asset = db.scalars(select(AssetORM).where(AssetORM.id == asset_id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return asset


@router.get("/{asset_id}/anomaly")
def get_anomaly_score(asset_id: str, db: Session = Depends(get_db)):
    """Zwraca ostatni zapisany wynik anomalii. 404 gdy brak danych."""
    _asset_or_404(db, asset_id)
    result = get_latest(db, asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Brak danych anomalii — uruchom /anomaly/refresh")
    return result


@router.get("/{asset_id}/anomaly/history")
def get_anomaly_history(asset_id: str, limit: int = 30, db: Session = Depends(get_db)):
    """Zwraca historię wyników anomalii (domyślnie ostatnie 30 dni)."""
    _asset_or_404(db, asset_id)
    return get_history(db, asset_id, limit=limit)


@router.post("/{asset_id}/anomaly/refresh")
def refresh_anomaly_score(asset_id: str, db: Session = Depends(get_db)):
    """Trenuje Isolation Forest i oblicza anomaly score dla aktywa."""
    asset = _asset_or_404(db, asset_id)
    if asset.type != "stock":
        raise HTTPException(status_code=400, detail="Anomaly detection dostępny tylko dla stocks")
    return train_and_score(db, asset_id)