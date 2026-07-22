from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.mappers import sync_log_to_schema
from app.repositories.assets import get_asset, list_assets
from app.repositories.sync_logs import list_sync_logs
from app.schemas.common import AssetType
from app.schemas.sync import SyncLogResponse, SyncResponse
from app.services.scheduler import scheduler
from app.services.feature_builder import rebuild_asset_features_and_forecasts
from app.services.outcome_evaluator import evaluate_asset_outcomes
from app.services.bootstrap import bootstrap_asset
from app.services.sync import log_sync_error, log_sync_success, sync_news_for_asset, sync_prices_for_asset, backfill_news_for_asset

router = APIRouter(tags=["sync"])


@router.get("/config/providers")
def provider_config() -> dict[str, object]:
    return {
        "price_provider_gpw": "EODHD -> Yahoo Finance",
        "price_provider_usa": "Massive -> Twelve Data -> Alpha Vantage -> Finnhub",
        "stock_news_provider": "Finnhub",
        "search_news_provider": "Alpha Vantage",
        "eodhd_configured": bool(settings.eodhd_api_key),
        "rapidapi_price_fallback_enabled": settings.rapidapi_price_fallback_enabled,
        "alphavantage_news_fallback_enabled": settings.alphavantage_news_fallback_enabled,
        "gpw_price_crosscheck_tolerance_pct": settings.gpw_price_crosscheck_tolerance_pct,
        "alpha_vantage_configured": bool(settings.alphavantage_api_key),
        "finnhub_configured": bool(settings.finnhub_api_key),
        "auto_sync_enabled": settings.auto_sync_enabled,
        "auto_sync_interval_minutes": settings.auto_sync_interval_minutes,
        "asset_provider_config": settings.asset_provider_config,
    }


@router.get("/scheduler/status")
def scheduler_status() -> dict[str, object]:
    jobs = scheduler.get_jobs() if scheduler.running else []
    return {
        "running": scheduler.running,
        "job_count": len(jobs),
        "jobs": [{"id": job.id, "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None} for job in jobs],
    }


@router.get("/sync/logs", response_model=list[SyncLogResponse])
def get_sync_logs(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> list[SyncLogResponse]:
    return [sync_log_to_schema(row) for row in list_sync_logs(db, limit=limit)]


@router.post("/sync/prices/{asset_id}", response_model=SyncResponse)
def sync_prices(asset_id: str, db: Session = Depends(get_db)) -> SyncResponse:
    asset = get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    try:
        result = sync_prices_for_asset(db, asset)
        log_sync_success(db, asset.id, "prices", result)
        rebuild_asset_features_and_forecasts(db, asset)
        return result
    except HTTPException as exc:
        log_sync_error(db, asset.id, "prices", str(exc.detail))
        raise


@router.post("/sync/news/{asset_id}", response_model=SyncResponse)
def sync_news(asset_id: str, db: Session = Depends(get_db)) -> SyncResponse:
    asset = get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    try:
        result = sync_news_for_asset(db, asset)
        log_sync_success(db, asset.id, "news", result)
        rebuild_asset_features_and_forecasts(db, asset)
        return result
    except HTTPException as exc:
        log_sync_error(db, asset.id, "news", str(exc.detail))
        raise


@router.post("/sync/all", response_model=list[SyncResponse])
def sync_all(db: Session = Depends(get_db)) -> list[SyncResponse]:
    results: list[SyncResponse] = []
    for asset in list_assets(db):
        try:
            if asset.id in {"gold", "silver"} or asset.type == AssetType.STOCK.value:
                result = sync_prices_for_asset(db, asset)
                log_sync_success(db, asset.id, "prices", result)
                rebuild_asset_features_and_forecasts(db, asset)
                results.append(result)
        except HTTPException as exc:
            log_sync_error(db, asset.id, "prices", str(exc.detail))
            results.append(SyncResponse(asset_id=asset.id, provider="price-sync", inserted=0, skipped=0, detail=f"Skipped prices: {exc.detail}"))

        try:
            result = sync_news_for_asset(db, asset)
            log_sync_success(db, asset.id, "news", result)
            rebuild_asset_features_and_forecasts(db, asset)
            results.append(result)
        except HTTPException as exc:
            log_sync_error(db, asset.id, "news", str(exc.detail))
            results.append(SyncResponse(asset_id=asset.id, provider="news-sync", inserted=0, skipped=0, detail=f"Skipped news: {exc.detail}"))
    return results


@router.post("/sync/news-backfill/{asset_id}")
def backfill_news(
    asset_id: str,
    months_back: int = Query(default=12, ge=1, le=24),
    db: Session = Depends(get_db),
) -> dict:
    """
    Pobiera historyczne newsy dla aktywa za ostatnie N miesięcy.
    Używa Finnhub (US stocks) + Alpha Vantage (wszystkie).
    Ostrożnie z limitami API — AV ma 25 req/dzień na free tier.
    """
    asset = get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return backfill_news_for_asset(db, asset, months_back=months_back)


@router.post("/sync/news-backfill-all")
def backfill_news_all(
    months_back: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    Backfill historycznych newsów dla wszystkich aktywów.
    Domyślnie 6 miesięcy żeby nie wyczerpać limitu AV w jednym wywołaniu.
    """
    results = []
    for asset in list_assets(db):
        try:
            result = backfill_news_for_asset(db, asset, months_back=months_back)
            results.append(result)
        except Exception as exc:
            results.append({"asset_id": asset.id, "error": str(exc)})
    return results


@router.post("/assets/{asset_id}/bootstrap")
def bootstrap_asset(asset_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    asset = get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")

    report: dict[str, object] = {
        "asset_id": asset_id,
        "prices": {"ok": False, "detail": "not attempted"},
        "news": {"ok": False, "detail": "not attempted"},
        "features": {"ok": False, "detail": "not attempted"},
        "outcomes": {"ok": False, "detail": "not attempted"},
        "errors": [],
    }

    try:
        if asset.id in {"gold", "silver"} or asset.type == AssetType.STOCK.value:
            price_result = sync_prices_for_asset(db, asset)
            log_sync_success(db, asset.id, "prices", price_result)
            report["prices"] = {"ok": True, "detail": price_result.detail, "inserted": price_result.inserted, "skipped": price_result.skipped}
        else:
            report["prices"] = {"ok": False, "detail": "No automatic price provider configured for this asset."}
    except HTTPException as exc:
        log_sync_error(db, asset.id, "prices", str(exc.detail))
        report["prices"] = {"ok": False, "detail": str(exc.detail)}
        report["errors"].append(f"prices: {exc.detail}")

    try:
        news_result = sync_news_for_asset(db, asset)
        log_sync_success(db, asset.id, "news", news_result)
        report["news"] = {"ok": True, "detail": news_result.detail, "inserted": news_result.inserted, "skipped": news_result.skipped}
    except HTTPException as exc:
        log_sync_error(db, asset.id, "news", str(exc.detail))
        report["news"] = {"ok": False, "detail": str(exc.detail)}
        report["errors"].append(f"news: {exc.detail}")

    try:
        snapshot = rebuild_asset_features_and_forecasts(db, asset)
        if snapshot is None:
            report["features"] = {"ok": False, "detail": "Not enough price history to build features yet."}
            report["errors"].append("features: Not enough price history to build features yet.")
        else:
            report["features"] = {"ok": True, "detail": "Features, forecasts and thesis rebuilt.", "snapshot_at": str(snapshot.snapshot_at)}
    except Exception as exc:
        report["features"] = {"ok": False, "detail": str(exc)}
        report["errors"].append(f"features: {exc}")

    try:
        evaluated = evaluate_asset_outcomes(db, asset_id, limit=100)
        report["outcomes"] = {"ok": True, "detail": "Thesis outcomes rebuilt.", "evaluated": evaluated}
    except Exception as exc:
        report["outcomes"] = {"ok": False, "detail": str(exc)}
        report["errors"].append(f"outcomes: {exc}")

    report["ok"] = len(report["errors"]) == 0
    return report
