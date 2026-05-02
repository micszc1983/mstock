from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AssetORM, DecisionSnapshotORM, MLPredictionORM, SyncLogORM
from app.repositories.alerts import get_recent_similar_alert, insert_alert, list_alert_rules
from app.repositories.features import get_latest_feature_snapshot, list_feature_history
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.prices import list_prices
from app.utils.datetime import ensure_utc, now_utc


def _within_cooldown(alert_row, cooldown_minutes: int) -> bool:
    if alert_row is None:
        return False
    created_at = ensure_utc(alert_row.created_at)
    return now_utc() - created_at < timedelta(minutes=cooldown_minutes)


def _default_rule_map():
    return {
        "fragility_high":             {"threshold": 60.0, "severity": "high",     "cooldown_minutes": 120},
        "dominant_narrative_changed": {"threshold": 1.0,  "severity": "medium",   "cooldown_minutes": 180},
        "forecast_downgrade":         {"threshold": 1.0,  "severity": "high",     "cooldown_minutes": 180},
        "signal_flip_kup_sprzedaj":   {"threshold": 1.0,  "severity": "critical", "cooldown_minutes": 1440},
        "price_drop_session":         {"threshold": -5.0, "severity": "critical", "cooldown_minutes": 1440},
        "dead_data":                  {"threshold": 2.0,  "severity": "critical", "cooldown_minutes": 240},
        "data_quality_low":           {"threshold": 50.0, "severity": "critical", "cooldown_minutes": 1440},
        "ml_bearish_divergence":      {"threshold": 0.4,  "severity": "high",     "cooldown_minutes": 360},
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

    # 4. signal_flip_kup_sprzedaj — KUP → SPRZEDAJ bez TRZYMAJ pośrodku
    last2_decisions = db.scalars(
        select(DecisionSnapshotORM)
        .where(DecisionSnapshotORM.asset_id == asset_id)
        .order_by(DecisionSnapshotORM.snapshot_at.desc())
        .limit(2)
    ).all()
    if len(last2_decisions) == 2:
        current_label = last2_decisions[0].action_label
        previous_label = last2_decisions[1].action_label
        if previous_label == "KUP" and current_label == "SPRZEDAJ":
            cfg = _get_rule_config(db, "signal_flip_kup_sprzedaj")
            prev = get_recent_similar_alert(db, asset_id, "signal_flip_kup_sprzedaj")
            if not _within_cooldown(prev, cfg.get("cooldown_minutes", 1440)):
                insert_alert(
                    db=db,
                    asset_id=asset_id,
                    created_at=now_utc(),
                    alert_type="signal_flip_kup_sprzedaj",
                    severity="critical",
                    title=f"{asset_id.upper()}: sygnal zmienil sie KUP -> SPRZEDAJ",
                    message=f"Rekomendacja zmienila sie bezposrednio z KUP na SPRZEDAJ (bez TRZYMAJ posrodku).",
                    status="new",
                    trigger_value=1.0,
                    threshold_value=1.0,
                    snapshot_json=json.dumps({
                        "previous_label": previous_label,
                        "current_label": current_label,
                        "snapshot_at": str(last2_decisions[0].snapshot_at),
                    }),
                )
                created += 1

    # 5. price_drop_session — spadek ceny >5% między ostatnimi dwoma sesjami
    prices = list_prices(db, asset_id, limit=2)
    if len(prices) == 2:
        prev_close = prices[0].close
        last_close = prices[1].close
        last_ts = ensure_utc(prices[1].timestamp) if hasattr(prices[1], "timestamp") else None
        # Freshness check: alertuj tylko gdy nowa cena pochodzi z ostatnich 36h
        price_is_fresh = last_ts is None or (now_utc() - last_ts) < timedelta(hours=36)
        if prev_close and last_close and prev_close > 0 and price_is_fresh:
            drop_pct = (last_close - prev_close) / prev_close * 100.0
            if drop_pct < -5.0:
                cfg = _get_rule_config(db, "price_drop_session")
                prev_alert = get_recent_similar_alert(db, asset_id, "price_drop_session")
                if not _within_cooldown(prev_alert, cfg.get("cooldown_minutes", 1440)):
                    insert_alert(
                        db=db,
                        asset_id=asset_id,
                        created_at=now_utc(),
                        alert_type="price_drop_session",
                        severity="critical",
                        title=f"{asset_id.upper()}: gwaltowny spadek ceny {drop_pct:.1f}%",
                        message=f"Cena spadla o {abs(drop_pct):.1f}% (z {prev_close:.2f} do {last_close:.2f}) w ciagu jednej sesji.",
                        status="new",
                        trigger_value=round(drop_pct, 2),
                        threshold_value=-5.0,
                        snapshot_json=json.dumps({
                            "prev_close": prev_close,
                            "last_close": last_close,
                            "drop_pct": round(drop_pct, 2),
                        }),
                    )
                    created += 1

    # 6. dead_data — ostatnie 2+ cykle synchronizacji zakończyły się błędem
    last2_syncs = db.scalars(
        select(SyncLogORM)
        .where(SyncLogORM.asset_id == asset_id, SyncLogORM.sync_type == "prices")
        .order_by(SyncLogORM.created_at.desc())
        .limit(2)
    ).all()
    if len(last2_syncs) >= 2 and all(s.status == "error" for s in last2_syncs):
        cfg = _get_rule_config(db, "dead_data")
        prev_alert = get_recent_similar_alert(db, asset_id, "dead_data")
        if not _within_cooldown(prev_alert, cfg.get("cooldown_minutes", 120)):
            insert_alert(
                db=db,
                asset_id=asset_id,
                created_at=now_utc(),
                alert_type="dead_data",
                severity="critical",
                title=f"{asset_id.upper()}: martwe dane - 2 kolejne bledy synchronizacji",
                message=f"Pobieranie cen zakonczylo sie bledem przez {len(last2_syncs)} kolejne cykle synchronizacji.",
                status="new",
                trigger_value=float(len(last2_syncs)),
                threshold_value=2.0,
                snapshot_json=json.dumps({
                    "errors": [{"created_at": str(s.created_at), "detail": s.detail} for s in last2_syncs],
                }),
            )
            created += 1

    # 7. data_quality_low — overall_score poniżej progu
    try:
        from app.core.config import settings
        from app.services.data_quality import check_asset_quality
        asset_row = db.scalar(select(AssetORM).where(AssetORM.id == asset_id))
        if asset_row is not None:
            quality = check_asset_quality(db, asset_row)
            quality_pct = quality.overall_score * 100.0
            threshold = settings.sms_data_quality_threshold
            if quality_pct < threshold:
                cfg = _get_rule_config(db, "data_quality_low")
                prev_alert = get_recent_similar_alert(db, asset_id, "data_quality_low")
                if not _within_cooldown(prev_alert, cfg.get("cooldown_minutes", 1440)):
                    insert_alert(
                        db=db,
                        asset_id=asset_id,
                        created_at=now_utc(),
                        alert_type="data_quality_low",
                        severity="critical",
                        title=f"{asset_id.upper()}: niska jakosc danych ({quality_pct:.1f}%)",
                        message=f"Wskaznik jakosci danych spadl do {quality_pct:.1f}%, ponizej progu {threshold:.1f}%.",
                        status="new",
                        trigger_value=round(quality_pct, 2),
                        threshold_value=threshold,
                        snapshot_json=json.dumps({
                            "overall_score": quality.overall_score,
                            "threshold": threshold,
                        }),
                    )
                    created += 1
    except Exception as _dq_exc:
        pass  # nie przerywaj cyklu jeśli data_quality_check zawiedzie

    # 8. ml_bearish_divergence — ML mówi "down" gdy heurystyki wyglądają neutralnie/dobrze
    ml_pred = db.scalar(
        select(MLPredictionORM)
        .where(
            MLPredictionORM.asset_id == asset_id,
            MLPredictionORM.target_name == "target_up_5d",
        )
        .order_by(MLPredictionORM.snapshot_at.desc())
        .limit(1)
    )
    if ml_pred is not None and ml_pred.probability_up < 0.4:
        # Dywergencja tylko gdy heurystyki nie alarmują już same z siebie
        heuristics_not_alarming = (
            latest.fragility_score < 60
            and latest.trend_score > 40
        )
        if heuristics_not_alarming:
            cfg = _get_rule_config(db, "ml_bearish_divergence")
            prev = get_recent_similar_alert(db, asset_id, "ml_bearish_divergence")
            if not _within_cooldown(prev, cfg.get("cooldown_minutes", 360)):
                insert_alert(
                    db=db,
                    asset_id=asset_id,
                    created_at=now_utc(),
                    alert_type="ml_bearish_divergence",
                    severity="high",
                    title=f"{asset_id.upper()}: ML ostrzega przed spadkiem",
                    message=(
                        f"Model ML (5d) przewiduje spadek z prawdopodobienstwem "
                        f"{(1 - ml_pred.probability_up) * 100:.0f}% "
                        f"(prob_up={ml_pred.probability_up:.2f}), "
                        f"podczas gdy trend={latest.trend_score:.0f}, "
                        f"fragility={latest.fragility_score:.0f}."
                    ),
                    status="new",
                    trigger_value=round(ml_pred.probability_up, 3),
                    threshold_value=0.4,
                    snapshot_json=json.dumps({
                        "probability_up": ml_pred.probability_up,
                        "predicted_label": ml_pred.predicted_label,
                        "trend_score": latest.trend_score,
                        "fragility_score": latest.fragility_score,
                        "snapshot_at": str(ml_pred.snapshot_at),
                    }),
                )
                created += 1

    db.commit()
    return created
