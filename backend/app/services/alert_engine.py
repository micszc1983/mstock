from __future__ import annotations

import json
from datetime import timedelta

from app.utils.datetime import ensure_utc, now_utc

from sqlalchemy.orm import Session

from app.repositories.alerts import get_recent_similar_alert, insert_alert, list_alert_rules
from app.repositories.features import get_latest_feature_snapshot, list_feature_history
from app.repositories.forecasts import get_latest_forecasts


def _within_cooldown(alert_row, cooldown_minutes: int) -> bool:
    if alert_row is None:
        return False
    created_at = ensure_utc(alert_row.created_at)
    return now_utc() - created_at < timedelta(minutes=cooldown_minutes)


def _default_rule_map():
    return {
        "fragility_high": {"threshold": 60.0, "severity": "high", "cooldown_minutes": 120},
        "dominant_narrative_changed": {"threshold": 1.0, "severity": "medium", "cooldown_minutes": 180},
        "forecast_downgrade": {"threshold": 1.0, "severity": "high", "cooldown_minutes": 180},
    }


def _get_rule_config(db: Session, alert_type: str) -> dict:
    defaults = _default_rule_map().get(alert_type, {"threshold": 1.0, "severity": "medium", "cooldown_minutes": 60})
    for rule in list_alert_rules(db):
        if rule.is_enabled and rule.alert_type == alert_type:
            try:
                threshold_json = json.loads(rule.threshold_json)
            except Exception:
                threshold_json = {}
            return {
                "threshold": float(threshold_json.get("threshold", defaults["threshold"])),
                "severity": rule.severity,
                "cooldown_minutes": rule.cooldown_minutes,
            }
    return defaults


def run_alert_engine(db: Session, asset_id: str) -> int:
    created = 0
    latest = get_latest_feature_snapshot(db, asset_id)
    history = list_feature_history(db, asset_id, limit=2)
    forecasts = get_latest_forecasts(db, asset_id)

    if latest is None:
        return 0

    # 1. fragility_high
    cfg = _get_rule_config(db, "fragility_high")
    if latest.fragility_score >= cfg["threshold"]:
        prev = get_recent_similar_alert(db, asset_id, "fragility_high")
        if not _within_cooldown(prev, cfg["cooldown_minutes"]):
            insert_alert(
                db=db,
                asset_id=asset_id,
                created_at=now_utc(),
                alert_type="fragility_high",
                severity=cfg["severity"],
                title=f"{asset_id.upper()}: fragility high",
                message=f"Fragility score reached {latest.fragility_score:.2f}, above threshold {cfg['threshold']:.2f}.",
                status="new",
                trigger_value=float(latest.fragility_score),
                threshold_value=float(cfg["threshold"]),
                snapshot_json=json.dumps(
                    {
                        "snapshot_at": latest.snapshot_at.isoformat() if hasattr(latest.snapshot_at, "isoformat") else str(latest.snapshot_at),
                        "fragility_score": latest.fragility_score,
                        "divergence_score": latest.divergence_score,
                    }
                ),
            )
            created += 1

    # 2. dominant_narrative_changed
    if len(history) >= 2:
        current = history[0]
        previous = history[1]
        cfg = _get_rule_config(db, "dominant_narrative_changed")
        if current.dominant_narrative and previous.dominant_narrative and current.dominant_narrative != previous.dominant_narrative:
            prev = get_recent_similar_alert(db, asset_id, "dominant_narrative_changed")
            if not _within_cooldown(prev, cfg["cooldown_minutes"]):
                insert_alert(
                    db=db,
                    asset_id=asset_id,
                    created_at=now_utc(),
                    alert_type="dominant_narrative_changed",
                    severity=cfg["severity"],
                    title=f"{asset_id.upper()}: dominant narrative changed",
                    message=f"Narrative changed from {previous.dominant_narrative} to {current.dominant_narrative}.",
                    status="new",
                    trigger_value=1.0,
                    threshold_value=1.0,
                    snapshot_json=json.dumps(
                        {
                            "previous": previous.dominant_narrative,
                            "current": current.dominant_narrative,
                            "snapshot_at": str(current.snapshot_at),
                        }
                    ),
                )
                created += 1

    # 3. forecast_downgrade
    if forecasts:
        cfg = _get_rule_config(db, "forecast_downgrade")
        downish = [f for f in forecasts if f.direction == "down"]
        if downish:
            prev = get_recent_similar_alert(db, asset_id, "forecast_downgrade")
            if not _within_cooldown(prev, cfg["cooldown_minutes"]):
                sample = downish[0]
                insert_alert(
                    db=db,
                    asset_id=asset_id,
                    created_at=now_utc(),
                    alert_type="forecast_downgrade",
                    severity=cfg["severity"],
                    title=f"{asset_id.upper()}: forecast downgrade",
                    message=f"Forecast horizon {sample.horizon} points down with confidence {sample.confidence:.2f}.",
                    status="new",
                    trigger_value=float(sample.confidence),
                    threshold_value=float(cfg["threshold"]),
                    snapshot_json=json.dumps(
                        {
                            "horizon": sample.horizon,
                            "direction": sample.direction,
                            "confidence": sample.confidence,
                            "expected_return_pct": sample.expected_return_pct,
                        }
                    ),
                )
                created += 1

    db.commit()
    return created
