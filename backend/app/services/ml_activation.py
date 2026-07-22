"""Automatic, per-model activation gate for live recommendations.

Active champions always keep scoring in shadow mode.  Their predictions become
eligible for live recommendations only after training safeguards, fresh drift
monitoring and enough post-deployment outcomes all pass.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from statistics import mean

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import MLModelMonitorORM, MLModelRunORM
from app.repositories.ml import get_setting, upsert_setting
from app.utils.datetime import ensure_utc, now_utc


_EMERGENCY_KEY = "ml_emergency_disabled"


@dataclass(frozen=True)
class ActivationDecision:
    model_run_id: int
    eligible: bool
    state: str
    reason: str
    sample_size: int = 0
    feature_psi: float | None = None
    avg_net_return_pct: float | None = None
    profit_factor: float | None = None
    calibration_error: float | None = None


@dataclass(frozen=True)
class ActivatedPrediction:
    asset_id: str
    target_name: str
    probability_up: float
    predicted_label: str
    model_run_id: int
    model_scope: str
    snapshot_at: object


def emergency_disabled(db: Session) -> bool:
    row = get_setting(db, _EMERGENCY_KEY)
    return row is not None and row.setting_value.lower() == "true"


def set_emergency_disabled(db: Session, disabled: bool) -> None:
    upsert_setting(db, _EMERGENCY_KEY, "true" if disabled else "false")
    db.commit()


def training_metrics_are_safe(metrics: dict) -> bool:
    profit_factor = metrics.get("holdout_profit_factor")
    return (
        int(metrics.get("holdout_trades", 0)) >= settings.challenger_min_holdout_trades
        and float(metrics.get("holdout_avg_net_return_pct", 0.0)) > 0
        and (profit_factor is None or float(profit_factor) > 1.0)
        and int(metrics.get("cv_folds", 0)) >= 2
        # Runs created before DSR persistence were already promoted by the old
        # safety gate; keep them compatible and let live monitoring arbitrate.
        and float(metrics.get("deflated_sharpe_ratio", 1.0) or 0.0) >= 0.20
        and (not settings.ml_cpcv_enabled or int(metrics.get("cpcv_paths", 0)) >= 2)
        and float(metrics.get("pbo", 0.0) or 0.0) <= settings.ml_pbo_max
    )


def _metrics(run: MLModelRunORM) -> dict:
    try:
        return json.loads(run.metrics_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def latest_monitor_for_run(db: Session, model_run_id: int) -> MLModelMonitorORM | None:
    return db.scalar(
        select(MLModelMonitorORM)
        .where(MLModelMonitorORM.model_run_id == model_run_id)
        .order_by(MLModelMonitorORM.checked_at.desc())
        .limit(1)
    )


def activation_decision(
    db: Session, run: MLModelRunORM, monitor: MLModelMonitorORM | None = None,
    emergency: bool | None = None,
) -> ActivationDecision:
    if emergency if emergency is not None else emergency_disabled(db):
        return ActivationDecision(run.id, False, "disabled", "awaryjna blokada ML")
    if not run.is_active or run.deployment_role != "champion":
        return ActivationDecision(run.id, False, "shadow", "model nie jest aktywnym championem")
    if not training_metrics_are_safe(_metrics(run)):
        return ActivationDecision(run.id, False, "shadow", "walidacja treningowa nie potwierdza przewagi")
    monitor = monitor or latest_monitor_for_run(db, run.id)
    if monitor is None:
        return ActivationDecision(run.id, False, "shadow", "brak monitoringu po wdrożeniu")

    common = dict(
        sample_size=monitor.sample_size,
        feature_psi=monitor.feature_psi,
        avg_net_return_pct=monitor.recent_avg_net_return_pct,
        profit_factor=monitor.recent_profit_factor,
        calibration_error=monitor.calibration_error,
    )
    if monitor.is_degraded:
        return ActivationDecision(run.id, False, "degraded", "drift lub degradacja wyników", **common)
    checked_at = ensure_utc(monitor.checked_at)
    max_age_minutes = max(180, int(getattr(settings, "auto_sync_interval_minutes", 60)) * 3)
    if now_utc() - checked_at > timedelta(minutes=max_age_minutes):
        return ActivationDecision(run.id, False, "shadow", "monitoring jest nieaktualny", **common)
    minimum = settings.ml_monitor_min_outcomes
    if monitor.sample_size < minimum:
        return ActivationDecision(
            run.id, False, "shadow",
            f"za mało wyników po wdrożeniu ({monitor.sample_size}/{minimum})", **common,
        )
    if monitor.recent_avg_net_return_pct is None or monitor.recent_avg_net_return_pct <= 0:
        return ActivationDecision(run.id, False, "shadow", "brak dodatniej przewagi live po kosztach", **common)
    if monitor.recent_profit_factor is not None and monitor.recent_profit_factor <= 1.0:
        return ActivationDecision(run.id, False, "shadow", "profit factor live nie przekracza 1", **common)
    if monitor.calibration_error is None or monitor.calibration_error > 0.18:
        return ActivationDecision(run.id, False, "shadow", "kalibracja live jest niepotwierdzona", **common)
    return ActivationDecision(run.id, True, "eligible", "spełnia automatyczną bramkę", **common)


def _latest_monitor_map(db: Session) -> dict[int, MLModelMonitorORM]:
    latest = (
        select(
            MLModelMonitorORM.model_run_id.label("model_run_id"),
            func.max(MLModelMonitorORM.checked_at).label("checked_at"),
        )
        .group_by(MLModelMonitorORM.model_run_id)
        .subquery()
    )
    rows = db.scalars(
        select(MLModelMonitorORM).join(
            latest,
            and_(
                MLModelMonitorORM.model_run_id == latest.c.model_run_id,
                MLModelMonitorORM.checked_at == latest.c.checked_at,
            ),
        )
    ).all()
    return {row.model_run_id: row for row in rows}


def automatic_activation_summary(db: Session) -> dict:
    runs = list(db.scalars(
        select(MLModelRunORM).where(
            MLModelRunORM.is_active.is_(True),
            MLModelRunORM.deployment_role == "champion",
        )
    ).all())
    monitors = _latest_monitor_map(db)
    disabled = emergency_disabled(db)
    decisions = [
        activation_decision(db, run, monitors.get(run.id), emergency=disabled)
        for run in runs
    ]
    eligible = sum(decision.eligible for decision in decisions)
    degraded = sum(decision.state == "degraded" for decision in decisions)
    shadow = len(decisions) - eligible - degraded
    mode = (
        "emergency_off" if disabled else
        "heuristic" if eligible == 0 else
        "ml" if eligible == len(decisions) else
        "ml_partial"
    )
    return {
        "mode": mode,
        "enabled": bool(eligible) and not disabled,
        "emergency_disabled": disabled,
        "active_models": len(runs),
        "eligible_models": eligible,
        "shadow_models": shadow,
        "degraded_models": degraded,
        "decisions": decisions,
    }


def _candidate_runs(db: Session, asset_id: str, target_name: str):
    from app.repositories.assets import get_asset
    from app.repositories.ml import (
        get_active_market_model_runs, get_all_active_model_runs,
    )
    from app.services.recommendation_calibration import market_segment

    asset = get_asset(db, asset_id)
    market = market_segment(asset) if asset is not None else "OTHER"
    scopes = [
        ("asset", get_all_active_model_runs(db, target_name, asset_id=asset_id)),
        ("market", get_active_market_model_runs(db, target_name, market)),
        ("global", get_all_active_model_runs(db, target_name, asset_id=None)),
    ]
    seen = set()
    for scope, runs in scopes:
        unique = [run for run in runs if run.id not in seen]
        seen.update(run.id for run in unique)
        if unique:
            yield scope, unique


def _score_runs(db: Session, asset_id: str, target_name: str, scope: str, runs: list[MLModelRunORM]):
    from app.repositories.ml import list_training_rows_for_target
    from app.services.ml_foundation import _feature_vector
    from app.services.ml_models.registry import predict_proba_single

    vec, feature = _feature_vector(db, asset_id)
    if vec is None or feature is None:
        return None
    from app.services.meta_labeling import enrich_meta_features, live_primary_meta_features
    if target_name == "target_meta_label":
        vec = enrich_meta_features(vec, live=live_primary_meta_features(db, asset_id, vec))
    history = list_training_rows_for_target(db, target_name, asset_id=asset_id)[-25:]
    X_full = [
        enrich_meta_features(json.loads(row.feature_json), row=row)
        if target_name == "target_meta_label" else json.loads(row.feature_json)
        for row in history
    ] + [vec]
    probabilities = []
    used = []
    for run in runs:
        try:
            probabilities.append(predict_proba_single(run.model_name, run.model_path, X_full))
            used.append(run)
        except Exception:
            continue
    if not probabilities:
        return None
    probability = float(mean(probabilities))
    if target_name == "target_meta_label":
        from app.services.meta_thresholds import calibrated_meta_threshold
        from app.repositories.assets import get_asset
        from app.services.recommendation_calibration import market_segment
        threshold = calibrated_meta_threshold(
            db, market_segment(get_asset(db, asset_id)), feature.regime_label,
        ).threshold
        label = "trade" if probability >= threshold else "skip"
    elif target_name == "target_triple_barrier":
        label = "upper" if probability >= 0.5 else "lower"
    else:
        label = "up" if probability >= 0.5 else "down"
    return ActivatedPrediction(
        asset_id=asset_id, target_name=target_name, probability_up=probability,
        predicted_label=label, model_run_id=used[0].id, model_scope=scope,
        snapshot_at=feature.snapshot_at,
    )


def get_eligible_prediction(
    db: Session, asset_id: str, target_name: str,
) -> ActivatedPrediction | None:
    """Live prediction with asset -> market -> global eligible fallback."""
    if emergency_disabled(db):
        return None
    from app.repositories.features import get_latest_feature_snapshot
    from app.repositories.ml import get_latest_prediction

    latest_feature = get_latest_feature_snapshot(db, asset_id)
    cached = get_latest_prediction(db, asset_id, target_name)
    for scope, runs in _candidate_runs(db, asset_id, target_name):
        eligible = [run for run in runs if activation_decision(db, run, emergency=False).eligible]
        if not eligible:
            continue
        eligible_ids = {run.id for run in eligible}
        if (
            cached is not None and cached.model_run_id in eligible_ids
            and latest_feature is not None
            and ensure_utc(cached.snapshot_at).date() == ensure_utc(latest_feature.snapshot_at).date()
        ):
            return ActivatedPrediction(
                asset_id=cached.asset_id, target_name=cached.target_name,
                probability_up=cached.probability_up, predicted_label=cached.predicted_label,
                model_run_id=cached.model_run_id, model_scope=scope,
                snapshot_at=cached.snapshot_at,
            )
        return _score_runs(db, asset_id, target_name, scope, eligible)
    return None
