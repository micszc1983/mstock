from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
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
    asset = db.scalars(select(AssetORM).where(AssetORM.id == asset_id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return asset


@router.get("/intraday/signals-summary")
def intraday_signals_summary(
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    db: Session = Depends(get_db),
):
    """Lekki, zbiorczy stan BUY/SELL dla selektora aktywów.

    Zastępuje osobne żądanie HTTP dla każdej spółki. Sygnały są liczone
    wyłącznie z zapisanych świec; endpoint nie uruchamia synchronizacji danych.
    """
    asset_ids = db.scalars(
        select(AssetORM.id).where(AssetORM.type == "stock").order_by(AssetORM.id)
    ).all()
    summary: dict[str, str | None] = {}
    for asset_id in asset_ids:
        payload = get_latest_signals(db, asset_id, resolution=resolution)
        signals = payload.get("signals", [])
        if any(signal.get("type") == "BUY" and signal.get("strength", 0) >= 0.6 for signal in signals):
            summary[asset_id] = "BUY"
        elif any(signal.get("type") == "SELL" and signal.get("strength", 0) >= 0.6 for signal in signals):
            summary[asset_id] = "SELL"
        else:
            summary[asset_id] = None
    return {"resolution": resolution, "signals": summary}


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


@router.get("/{asset_id}/intraday/full")
def intraday_full(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    candle_limit: int = Query(200, ge=10, le=500),
    vp_limit: int = Query(300, ge=20, le=500),
    benchmark: str = Query("qqq"),
    db: Session = Depends(get_db),
):
    """Zwraca wszystkie dane intraday w jednym żądaniu."""
    _asset_or_404(db, asset_id)
    candles_raw = get_candles(db, asset_id, resolution=resolution, limit=candle_limit)
    candles = [
        {
            "timestamp": c.timestamp.isoformat(),
            "open": c.open, "high": c.high, "low": c.low, "close": c.close,
            "volume": c.volume, "rsi": c.rsi, "ema9": c.ema9, "ema20": c.ema20,
            "macd": c.macd, "macd_signal": c.macd_signal,
            "bb_upper": c.bb_upper, "bb_lower": c.bb_lower,
            "volume_ratio": c.volume_ratio, "vwap": c.vwap,
        }
        for c in candles_raw
    ]
    signals = get_latest_signals(db, asset_id, resolution=resolution)
    volume_profile = get_volume_profile(db, asset_id, resolution=resolution, limit=vp_limit)
    rs = get_relative_strength_intraday(db, asset_id, resolution=resolution, benchmark_id=benchmark)

    anomaly = None
    try:
        from app.services.anomaly_service import get_latest as get_latest_anomaly
        anomaly = get_latest_anomaly(db, asset_id)
    except Exception:
        pass

    insider = None
    try:
        from app.services.insider_service import get_insider_sentiment
        insider = get_insider_sentiment(db, asset_id)
    except Exception:
        pass

    pead = None
    try:
        from app.services.pead_service import analyze_pead
        pead = analyze_pead(db, asset_id)
    except Exception:
        pass

    return {
        "candles": candles,
        "signals": signals,
        "volume_profile": volume_profile,
        "relative_strength": rs,
        "anomaly": anomaly,
        "insider": insider,
        "pead": pead,
    }


@router.get("/{asset_id}/intraday/backtest")
def intraday_backtest_latest(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60)$"),
    db: Session = Depends(get_db),
):
    """Zwraca ostatni zapisany wynik backtestingu + skalibrowane progi."""
    _asset_or_404(db, asset_id)
    from app.services.intraday_backtest_service import get_latest
    result = get_latest(db, asset_id, resolution)
    if result is None:
        raise HTTPException(status_code=404, detail="Brak backtestingu — uruchom POST /intraday/backtest/run")
    return result


@router.post("/{asset_id}/intraday/backtest/run")
def intraday_backtest_run(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60)$"),
    lookback_days: int = Query(30, ge=5, le=90),
    initial_capital: float = Query(10000.0, gt=0, le=100000000),
    risk_per_trade_pct: float = Query(1.0, gt=0, le=5),
    max_position_pct: float = Query(25.0, gt=0, le=100),
    commission_pct: float = Query(0.05, ge=0, le=5),
    slippage_pct: float = Query(0.05, ge=0, le=5),
    db: Session = Depends(get_db),
):
    """Uruchamia backtest + kalibrację progów na danych historycznych."""
    asset = _asset_or_404(db, asset_id)
    if asset.type != "stock":
        raise HTTPException(status_code=400, detail="Backtest dostępny tylko dla stocks")
    from app.services.intraday_backtest_service import run_backtest
    result = run_backtest(
        db, asset_id, resolution, lookback_days, initial_capital,
        risk_per_trade_pct, max_position_pct, commission_pct, slippage_pct,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.post("/{asset_id}/intraday/ai-analysis")
def intraday_ai_analysis(
    asset_id: str,
    resolution: str = Query("15", pattern=r"^(5|15|30|60|D)$"),
    db: Session = Depends(get_db),
):
    """Holograficzny kontekst — analiza AI na żądanie (Claude)."""
    asset = _asset_or_404(db, asset_id)
    if asset.type != "stock":
        raise HTTPException(status_code=400, detail="Analiza AI dostępna tylko dla stocks")
    from app.services.ai_analysis_service import analyze_intraday
    result = analyze_intraday(db, asset, resolution=resolution)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


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
