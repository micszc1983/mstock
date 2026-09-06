"""Monitoring driftu, kalibracji i wyników z ostrożnym rollbackiem championa."""
from __future__ import annotations

import json
from statistics import mean, median

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    MLModelMonitorORM, MLModelRunORM, MLPredictionORM, MLTrainingRowORM,
    RecommendationRecordORM,
)
from app.repositories.ml import list_training_rows_for_target
from app.services.ml_models.calibration import expected_calibration_error
from app.utils.datetime import ensure_utc, now_utc


_PSI_METHOD = "median_feature_psi_v2"


def _metrics(row: MLModelRunORM) -> dict:
    try:
        return json.loads(row.metrics_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _latest_monitor(db: Session, model_run_id: int) -> MLModelMonitorORM | None:
    return db.scalar(
        select(MLModelMonitorORM)
        .where(MLModelMonitorORM.model_run_id == model_run_id)
        .order_by(MLModelMonitorORM.checked_at.desc())
        .limit(1)
    )


def _prediction_feature_payloads(
    run: MLModelRunORM, db: Session, limit: int,
) -> list[dict]:
    """Cechy faktycznie przekazane modelowi po jego wdrożeniu."""
    rows = db.scalars(
        select(MLPredictionORM)
        .where(
            MLPredictionORM.model_run_id == run.id,
            MLPredictionORM.target_name == run.target_name,
            MLPredictionORM.snapshot_at > run.trained_at,
        )
        .order_by(MLPredictionORM.snapshot_at.desc())
        .limit(limit)
    ).all()
    payloads: list[dict] = []
    for row in rows:
        try:
            features = json.loads(row.raw_json).get("features")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(features, dict):
            payloads.append(features)
    return payloads


def _latest_feature_payloads(
    run: MLModelRunORM, db: Session, limit: int,
) -> list[dict]:
    """Fallback bez opóźnienia targetu; DESC+LIMIT gwarantuje najnowsze wiersze."""
    from app.services.meta_labeling import enrich_meta_features

    stmt = select(MLTrainingRowORM)
    if run.asset_id is not None:
        stmt = stmt.where(MLTrainingRowORM.asset_id == run.asset_id)
    elif run.market_segment is not None:
        stmt = stmt.where(MLTrainingRowORM.market_segment == run.market_segment)
    rows = db.scalars(
        stmt.order_by(MLTrainingRowORM.snapshot_at.desc()).limit(limit)
    ).all()
    payloads: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row.feature_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        # OOF meta-cechy są opcjonalne w fallbacku. Nigdy nie zastępujemy ich
        # zerami, bo taki rozkład nie odpowiada wejściu modelu live.
        if (
            run.target_name == "target_meta_label"
            and row.meta_primary_probability is not None
            and row.meta_primary_margin is not None
            and row.meta_model_disagreement is not None
        ):
            payload = enrich_meta_features(payload, row=row)
        payloads.append(payload)
    return payloads


def _population_stability_report(run: MLModelRunORM, db: Session) -> dict:
    import numpy as np

    metrics = _metrics(run)
    reference = metrics.get("feature_reference") or {}
    feature_names = metrics.get("feature_names") or []
    if not reference or not feature_names:
        return {"psi": None, "ready": False, "reason": "brak referencji cech"}
    window = max(30, int(settings.ml_drift_window_rows))
    minimum_live = max(10, int(settings.ml_drift_min_live_predictions))
    live_payloads = _prediction_feature_payloads(run, db, window)
    if len(live_payloads) >= minimum_live:
        payloads = live_payloads
        source = "live_predictions"
    else:
        payloads = _latest_feature_payloads(run, db, window)
        source = "latest_feature_snapshots"
    if len(payloads) < 30:
        return {
            "psi": None, "ready": False, "reason": "za mało obserwacji cech",
            "source": source, "sample_size": len(payloads),
            "live_prediction_samples": len(live_payloads),
        }

    scores: list[tuple[str, float]] = []
    excluded: list[str] = []
    for name in feature_names:
        ref = reference.get(name)
        if not ref:
            continue
        observed = [payload.get(name) for payload in payloads if payload.get(name) is not None]
        if len(observed) < 30:
            excluded.append(name)
            continue
        edges = [
            -float("inf") if value is None and index == 0 else
            float("inf") if value is None else float(value)
            for index, value in enumerate(ref["edges"])
        ]
        # Brak klucza w fallbacku oznacza, że cecha nie została wtedy
        # wyliczona (szczególnie OOF meta), a nie rzeczywistą wartość zero.
        current = np.asarray([float(value or 0.0) for value in observed])
        counts, _ = np.histogram(current, bins=edges)
        actual = counts / max(1, counts.sum())
        expected = np.asarray(ref["proportions"], dtype=float)
        size = min(len(actual), len(expected))
        actual = np.clip(actual[:size], 1e-6, None)
        expected = np.clip(expected[:size], 1e-6, None)
        actual /= actual.sum()
        expected /= expected.sum()
        score = float(np.sum((actual - expected) * np.log(actual / expected)))
        scores.append((name, score))
    if not scores:
        return {
            "psi": None, "ready": False, "reason": "brak wspólnych cech",
            "source": source, "sample_size": len(payloads),
            "live_prediction_samples": len(live_payloads),
        }

    values = [score for _, score in scores]
    ranked = sorted(scores, key=lambda item: item[1], reverse=True)
    return {
        # Mediana wykrywa szeroki drift i nie pozwala, by pojedyncza skokowa
        # cecha makro (np. miesięczne GS10) zablokowała cały model.
        "psi": round(float(median(values)), 6),
        "ready": True,
        "method": _PSI_METHOD,
        "source": source,
        "sample_size": len(payloads),
        "live_prediction_samples": len(live_payloads),
        "feature_count": len(scores),
        "excluded_features": excluded,
        "mean_feature_psi": round(float(mean(values)), 6),
        "max_feature_psi": round(float(max(values)), 6),
        "critical_feature_ratio": round(
            sum(score >= settings.ml_drift_psi_critical for score in values) / len(values), 6
        ),
        "top_drift_features": [
            {"feature": name, "psi": round(score, 6)} for name, score in ranked[:8]
        ],
    }


def _population_stability_index(run: MLModelRunORM, db: Session) -> float | None:
    """Kompatybilny interfejs zwracający odporny, zagregowany PSI."""
    return _population_stability_report(run, db).get("psi")


def _outcome_metrics(run: MLModelRunORM, db: Session) -> dict:
    # Dziennik przechowuje wszystkie zmiany rekomendacji w obrębie świecy.
    # Monitoring wyników używa wyłącznie końcowej rewizji, aby jednej sesji
    # nie liczyć wielokrotnie.
    latest_revision = (
        select(
            RecommendationRecordORM.asset_id.label("asset_id"),
            RecommendationRecordORM.snapshot_at.label("snapshot_at"),
            RecommendationRecordORM.model_version.label("model_version"),
            func.max(RecommendationRecordORM.revision).label("revision"),
        )
        .group_by(
            RecommendationRecordORM.asset_id,
            RecommendationRecordORM.snapshot_at,
            RecommendationRecordORM.model_version,
        )
        .subquery()
    )
    stmt = select(RecommendationRecordORM).join(
        latest_revision,
        and_(
            RecommendationRecordORM.asset_id == latest_revision.c.asset_id,
            RecommendationRecordORM.snapshot_at == latest_revision.c.snapshot_at,
            RecommendationRecordORM.model_version == latest_revision.c.model_version,
            RecommendationRecordORM.revision == latest_revision.c.revision,
        ),
    ).where(
        RecommendationRecordORM.meta_trade_probability.is_not(None),
        RecommendationRecordORM.realized_return_5d_pct.is_not(None),
    )
    if run.asset_id is not None:
        stmt = stmt.where(RecommendationRecordORM.asset_id == run.asset_id)
    elif run.market_segment is not None:
        stmt = stmt.where(RecommendationRecordORM.market == run.market_segment)
    rows = list(db.scalars(stmt.order_by(RecommendationRecordORM.snapshot_at.desc()).limit(100)).all())
    if not rows:
        return {"sample_size": 0}
    probabilities = [float(row.meta_trade_probability or 0.0) / 100.0 for row in rows]
    labels = [int(float(row.strategy_net_return_5d_pct or 0.0) > 0) for row in rows]
    calibration_error = expected_calibration_error(labels, probabilities)
    traded = [
        float(row.strategy_net_return_5d_pct or 0.0)
        for row in rows if row.action in {"BUY", "SELL"}
    ]
    wins = sum(value for value in traded if value > 0)
    losses = abs(sum(value for value in traded if value < 0))
    return {
        "sample_size": len(rows),
        "calibration_error": round(calibration_error, 6),
        "recent_avg_net_return_pct": round(mean(traded), 6) if traded else None,
        "recent_profit_factor": round(wins / losses, 6) if losses else None,
    }


def _prediction_outcome_metrics(run: MLModelRunORM, db: Session) -> dict:
    """Evaluate only shadow/live predictions whose snapshots post-date training."""
    predictions = list(db.scalars(
        select(MLPredictionORM)
        .where(
            MLPredictionORM.model_run_id == run.id,
            MLPredictionORM.target_name == run.target_name,
            MLPredictionORM.snapshot_at > run.trained_at,
        )
        .order_by(MLPredictionORM.snapshot_at.desc())
        .limit(100)
    ).all())
    if not predictions:
        return {"sample_size": 0}
    asset_ids = {prediction.asset_id for prediction in predictions}
    training_rows = list(db.scalars(
        select(MLTrainingRowORM)
        .where(MLTrainingRowORM.asset_id.in_(asset_ids))
        .order_by(MLTrainingRowORM.snapshot_at.desc())
        .limit(max(1000, len(asset_ids) * 400))
    ).all())
    by_key = {
        (row.asset_id, ensure_utc(row.snapshot_at).date()): row
        for row in training_rows
    }
    labels: list[int] = []
    probabilities: list[float] = []
    selected_returns: list[float] = []
    all_returns: list[float] = []
    from app.repositories.assets import get_asset
    from app.services.recommendation_calibration import market_segment, transaction_cost_pct

    for prediction in predictions:
        row = by_key.get((prediction.asset_id, ensure_utc(prediction.snapshot_at).date()))
        if row is None:
            continue
        target = getattr(row, run.target_name, None)
        if target is None:
            continue
        probability = float(prediction.probability_up)
        labels.append(int(target))
        probabilities.append(probability)
        if run.target_name == "target_meta_label":
            selected = prediction.predicted_label == "trade"
            value = float(row.meta_strategy_return_pct or 0.0) if selected else 0.0
        else:
            selected = True
            if run.target_name == "target_up_20d":
                raw = float(row.target_return_20d or 0.0)
            elif run.target_name == "target_triple_barrier":
                raw = float(row.triple_barrier_return_pct or 0.0)
            else:
                raw = float(row.target_return_5d or 0.0)
            predicts_positive = prediction.predicted_label in {"up", "upper"}
            asset = get_asset(db, prediction.asset_id)
            cost = transaction_cost_pct(market_segment(asset)) if asset is not None else 0.0
            value = (raw if predicts_positive else -raw) - cost
        all_returns.append(value)
        if selected:
            selected_returns.append(value)
    if not labels:
        return {"sample_size": 0}
    calibration_error = expected_calibration_error(labels, probabilities)
    wins = sum(value for value in selected_returns if value > 0)
    losses = abs(sum(value for value in selected_returns if value < 0))
    return {
        "sample_size": len(labels),
        "calibration_error": round(calibration_error, 6),
        "recent_avg_net_return_pct": round(mean(selected_returns), 6) if selected_returns else None,
        # None with positive average and no losses means an unbounded PF, not a failure.
        "recent_profit_factor": round(wins / losses, 6) if losses else None,
        "coverage_pct": round(len(selected_returns) / len(labels) * 100.0, 4),
        "strategy_avg_return_pct": round(mean(all_returns), 6) if all_returns else None,
    }


def _rollback_candidate(db: Session, run: MLModelRunORM) -> MLModelRunORM | None:
    stmt = select(MLModelRunORM).where(
        MLModelRunORM.target_name == run.target_name,
        MLModelRunORM.id != run.id,
        MLModelRunORM.deployment_role.in_(("archived", "challenger")),
    )
    if run.asset_id is not None:
        stmt = stmt.where(MLModelRunORM.asset_id == run.asset_id, MLModelRunORM.market_segment.is_(None))
    else:
        stmt = stmt.where(
            MLModelRunORM.asset_id.is_(None),
            MLModelRunORM.market_segment == run.market_segment,
        )
    for candidate in db.scalars(stmt.order_by(MLModelRunORM.trained_at.desc()).limit(20)).all():
        metrics = _metrics(candidate)
        if (
            int(metrics.get("holdout_trades", 0)) >= settings.challenger_min_holdout_trades
            and float(metrics.get("holdout_avg_net_return_pct", 0.0)) > 0
            and float(metrics.get("deflated_sharpe_ratio", 0.0)) >= 0.20
        ):
            return candidate
    return None


def monitor_active_models(db: Session, *, allow_rollback: bool = True) -> list[MLModelMonitorORM]:
    active = list(db.scalars(select(MLModelRunORM).where(
        MLModelRunORM.is_active.is_(True),
        MLModelRunORM.deployment_role == "champion",
    )).all())
    results = []
    for run in active:
        previous_monitor = _latest_monitor(db, run.id)
        drift = _population_stability_report(run, db)
        psi = drift.get("psi")
        outcomes = _prediction_outcome_metrics(run, db)
        if outcomes.get("sample_size", 0) == 0 and run.target_name == "target_meta_label":
            # Recommendation journal is a secondary live source for old meta
            # champions created before prediction-level monitoring existed.
            outcomes = _outcome_metrics(run, db)
        sample_size = int(outcomes.get("sample_size", 0))
        avg_return = outcomes.get("recent_avg_net_return_pct")
        profit_factor = outcomes.get("recent_profit_factor")
        calibration_error = outcomes.get("calibration_error")
        drift_warning = psi is not None and psi >= settings.ml_drift_psi_warning
        drift_critical_raw = psi is not None and psi >= settings.ml_drift_psi_critical
        previous_critical = False
        if previous_monitor is not None:
            try:
                previous_details = json.loads(previous_monitor.details_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                previous_details = {}
            previous_critical = (
                previous_details.get("psi_method") == _PSI_METHOD
                and bool(previous_details.get("drift_critical_raw"))
            )
        # Pojedynczy skok rozkładu przenosi model do shadow. Status degraded
        # wymaga potwierdzenia w kolejnym cyklu tego samego algorytmu PSI.
        drift_critical = drift_critical_raw and previous_critical
        drift_confirmation_pending = drift_critical_raw and not previous_critical
        performance_bad = (
            sample_size >= settings.ml_monitor_min_outcomes
            and avg_return is not None and avg_return <= 0
            and profit_factor is not None and profit_factor < 1.0
        )
        calibration_bad = (
            sample_size >= settings.ml_monitor_min_outcomes
            and calibration_error is not None and calibration_error > 0.18
        )
        degraded = drift_critical or performance_bad or (drift_warning and calibration_bad)
        action = "keep"
        replacement = None
        # Drift sam w sobie generuje alarm; rollback wymaga również danych wynikowych.
        if degraded and allow_rollback and sample_size >= settings.ml_monitor_min_outcomes:
            replacement = _rollback_candidate(db, run)
            if replacement is not None:
                run.is_active = False
                run.deployment_role = "archived"
                run.promotion_reason = "Automatyczny rollback: drift/degradacja wyników"
                replacement.is_active = True
                replacement.deployment_role = "champion"
                replacement.promotion_reason = f"Rollback z modelu {run.id} po monitoringu"
                action = "rollback"
            else:
                action = "alert"
        elif degraded:
            action = "alert"
        details = {
            "psi_method": _PSI_METHOD,
            "drift_ready": bool(drift.get("ready")),
            "drift_source": drift.get("source"),
            "drift_sample_size": drift.get("sample_size", 0),
            "live_prediction_samples": drift.get("live_prediction_samples", 0),
            "drift_warning": drift_warning,
            "drift_critical_raw": drift_critical_raw,
            "drift_critical": drift_critical,
            "drift_confirmation_pending": drift_confirmation_pending,
            "feature_count": drift.get("feature_count", 0),
            "excluded_features": drift.get("excluded_features", []),
            "mean_feature_psi": drift.get("mean_feature_psi"),
            "max_feature_psi": drift.get("max_feature_psi"),
            "critical_feature_ratio": drift.get("critical_feature_ratio"),
            "top_drift_features": drift.get("top_drift_features", []),
            "performance_bad": performance_bad, "calibration_bad": calibration_bad,
            "replacement_run_id": replacement.id if replacement else None,
            "coverage_pct": outcomes.get("coverage_pct"),
            "strategy_avg_return_pct": outcomes.get("strategy_avg_return_pct"),
            "activation_gate": (
                "eligible" if drift.get("ready") and not drift_confirmation_pending
                and not degraded and sample_size >= settings.ml_monitor_min_outcomes
                else "shadow"
            ),
        }
        row = MLModelMonitorORM(
            model_run_id=run.id, checked_at=now_utc(), asset_id=run.asset_id,
            market_segment=run.market_segment, feature_psi=psi,
            calibration_error=calibration_error,
            recent_avg_net_return_pct=avg_return, recent_profit_factor=profit_factor,
            sample_size=sample_size, is_degraded=degraded, action=action,
            details_json=json.dumps(details, ensure_ascii=False),
        )
        db.add(row)
        results.append(row)
    db.commit()
    rollback_runs = [row for row in results if row.action == "rollback"]
    if rollback_runs:
        from app.services.meta_thresholds import invalidate_meta_threshold_cache
        invalidate_meta_threshold_cache(db)
        from app.repositories.assets import list_assets
        from app.services.ml_foundation import score_asset
        from app.services.recommendation_calibration import market_segment
        for monitor in rollback_runs:
            run = db.get(MLModelRunORM, monitor.model_run_id)
            if run is None:
                continue
            if run.asset_id is not None:
                score_asset(db, run.asset_id, run.target_name)
            elif run.market_segment is not None:
                for asset in list_assets(db):
                    if market_segment(asset) == run.market_segment:
                        score_asset(db, asset.id, run.target_name)
    for row in results:
        db.refresh(row)
    return results


def latest_monitoring(db: Session, limit: int = 200) -> list[MLModelMonitorORM]:
    return list(db.scalars(
        select(MLModelMonitorORM).order_by(MLModelMonitorORM.checked_at.desc()).limit(limit)
    ).all())
