from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import AssetORM
from app.services.intraday_service import (
    get_candles,
    get_latest_signals,
    get_volume_profile,
    get_relative_strength_intraday,
    sync_intraday_candles,
)

router = APIRouter(prefix="/assets", tags=["intraday"])


def _asset_or_404(db: Session, asset_id: str) -> AssetORM:
    from sqlalchemy import select
    asset = db.scalars(select(AssetORM).where(AssetORM.id == asset_id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return asset


@router.get("/{asset_id}/intraday/candles")
def intraday_candles(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    limit: int = Query(200, ge=10, le=500),
    db: Session = Depends(get_db),
):
    _asset_or_404(db, asset_id)
    candles = get_candles(db, asset_id, resolution=resolution, limit=limit)
    return [
        {
            "timestamp": c.timestamp.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "rsi": c.rsi,
            "ema9": c.ema9,
            "ema20": c.ema20,
            "macd": c.macd,
            "macd_signal": c.macd_signal,
            "bb_upper": c.bb_upper,
            "bb_lower": c.bb_lower,
            "volume_ratio": c.volume_ratio,
            "vwap": c.vwap,
        }
        for c in candles
    ]


@router.get("/{asset_id}/intraday/signals")
def intraday_signals(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    db: Session = Depends(get_db),
):
    _asset_or_404(db, asset_id)
    return get_latest_signals(db, asset_id, resolution=resolution)


@router.get("/{asset_id}/intraday/relative-strength")
def intraday_relative_strength(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    benchmark: str = Query("qqq"),
    db: Session = Depends(get_db),
):
    _asset_or_404(db, asset_id)
    return get_relative_strength_intraday(db, asset_id, resolution=resolution, benchmark_id=benchmark)


@router.get("/{asset_id}/intraday/volume-profile")
def intraday_volume_profile(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    limit: int = Query(300, ge=20, le=500),
    db: Session = Depends(get_db),
):
    _asset_or_404(db, asset_id)
    return get_volume_profile(db, asset_id, resolution=resolution, limit=limit)


@router.post("/{asset_id}/intraday/sync")
def intraday_sync(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    db: Session = Depends(get_db),
):
    asset = _asset_or_404(db, asset_id)
    if asset.type != "stock":
        raise HTTPException(status_code=400, detail="Intraday dostępny tylko dla stocks")
    result = sync_intraday_candles(db, asset, resolution=resolution)
    return {"asset_id": asset_id, "resolution": resolution, **result}