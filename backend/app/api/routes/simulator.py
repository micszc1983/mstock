from __future__ import annotations

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import AssetORM, PricePointORM

router = APIRouter(prefix="/assets", tags=["simulator"])


def _asset_or_404(db: Session, asset_id: str) -> AssetORM:
    asset = db.scalars(select(AssetORM).where(AssetORM.id == asset_id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return asset


def _strip_tz(ts: datetime) -> datetime:
    return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts


@router.get("/{asset_id}/simulator/performance")
def simulator_performance(asset_id: str, db: Session = Depends(get_db)):
    asset = _asset_or_404(db, asset_id)

    cutoff = datetime.utcnow() - timedelta(days=400)
    prices = (
        db.query(PricePointORM)
        .filter(PricePointORM.asset_id == asset_id, PricePointORM.timestamp >= cutoff)
        .order_by(PricePointORM.timestamp.desc())
        .all()
    )

    if not prices:
        return {
            "asset_id": asset_id,
            "symbol": asset.symbol,
            "name": asset.name,
            "currency": asset.currency,
            "current_price": None,
            "last_price_date": None,
            "returns": [],
            "has_enough_data": False,
        }

    current_price = prices[0].close
    now_ts = _strip_tz(prices[0].timestamp)
    prices_asc = list(reversed(prices))

    def price_at_or_before(target: datetime) -> float | None:
        result = None
        for p in prices_asc:
            ts = _strip_tz(p.timestamp)
            if ts <= target + timedelta(hours=20):
                result = p.close
            else:
                break
        return result

    periods = [
        ("1w", "1 tydzień", 7),
        ("1m", "1 miesiąc", 30),
        ("3m", "3 miesiące", 90),
        ("1y", "1 rok", 365),
    ]

    returns = []
    for key, label, days in periods:
        target = now_ts - timedelta(days=days)
        start_price = price_at_or_before(target)
        if start_price and start_price > 0:
            ret_pct = (current_price - start_price) / start_price * 100
            returns.append({
                "key": key,
                "label": label,
                "days": days,
                "start_price": round(start_price, 4),
                "end_price": round(current_price, 4),
                "return_pct": round(ret_pct, 2),
                "available": True,
            })
        else:
            returns.append({
                "key": key,
                "label": label,
                "days": days,
                "start_price": None,
                "end_price": round(current_price, 4),
                "return_pct": None,
                "available": False,
            })

    return {
        "asset_id": asset_id,
        "symbol": asset.symbol,
        "name": asset.name,
        "currency": asset.currency,
        "current_price": round(current_price, 4),
        "last_price_date": prices[0].timestamp.isoformat(),
        "returns": returns,
        "has_enough_data": True,
    }
