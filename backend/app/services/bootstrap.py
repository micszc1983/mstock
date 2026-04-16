from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.assets import get_asset
from app.services.alert_engine import run_alert_engine
from app.services.feature_builder import rebuild_asset_features_and_forecasts
from app.services.news_enrichment import enrich_news_for_asset
from app.services.outcome_evaluator import evaluate_asset_outcomes
from app.services.sync import sync_news_for_asset, sync_prices_for_asset


def bootstrap_asset(db: Session, asset_id: str) -> dict:
    asset = get_asset(db, asset_id)
    if asset is None:
        return {"asset_id": asset_id, "errors": ["Unknown asset"], "prices_synced": False, "news_synced": False, "features_built": False, "news_enriched": False, "outcomes_built": False, "alerts_created": 0}

    report = {
        "asset_id": asset_id,
        "prices_synced": False,
        "news_synced": False,
        "features_built": False,
        "news_enriched": False,
        "outcomes_built": False,
        "alerts_created": 0,
        "errors": [],
    }

    try:
        sync_prices_for_asset(db, asset)
        report["prices_synced"] = True
    except Exception as exc:
        report["errors"].append(f"price sync: {exc}")

    try:
        sync_news_for_asset(db, asset)
        report["news_synced"] = True
    except Exception as exc:
        report["errors"].append(f"news sync: {exc}")

    try:
        snapshot = rebuild_asset_features_and_forecasts(db, asset)
        report["features_built"] = snapshot is not None
    except Exception as exc:
        report["errors"].append(f"feature rebuild: {exc}")

    try:
        enriched = enrich_news_for_asset(db, asset_id)
        report["news_enriched"] = enriched >= 0
    except Exception as exc:
        report["errors"].append(f"news enrich: {exc}")

    try:
        report["outcomes_built"] = evaluate_asset_outcomes(db, asset_id, limit=200) >= 0
    except Exception as exc:
        report["errors"].append(f"outcomes rebuild: {exc}")

    try:
        report["alerts_created"] = run_alert_engine(db, asset_id)
    except Exception as exc:
        report["errors"].append(f"alert engine: {exc}")

    return report
