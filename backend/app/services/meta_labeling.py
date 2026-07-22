"""Out-of-fold primary model dla klasycznego meta-labelingu."""
from __future__ import annotations

import json
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import MLModelRunORM
from app.repositories.assets import get_asset
from app.repositories.ml import list_training_rows_for_target
from app.services.ml_validation import purged_group_time_series_splits
from app.services.recommendation_calibration import market_segment, transaction_cost_pct
from app.utils.datetime import ensure_utc


META_FEATURE_NAMES = (
    "meta_primary_probability",
    "meta_primary_margin",
    "meta_model_disagreement",
)


def enrich_meta_features(features: dict, row=None, live: dict | None = None) -> dict:
    result = dict(features)
    values = live or {
        "meta_primary_probability": getattr(row, "meta_primary_probability", None),
        "meta_primary_margin": getattr(row, "meta_primary_margin", None),
        "meta_model_disagreement": getattr(row, "meta_model_disagreement", None),
    }
    for name in META_FEATURE_NAMES:
        result[name] = float(values.get(name) or 0.0)
    return result


def _primary_builders():
    from app.services.ml_models.logistic import _build_pipeline
    from app.services.ml_models.random_forest import _build_model as build_rf

    builders = [
        lambda y: _build_pipeline(),
        lambda y: build_rf(),
    ]
    try:
        from app.services.ml_models.xgboost_model import _build_model as build_xgb, _scale_pos_weight
        builders.append(lambda y: build_xgb(scale=_scale_pos_weight(y)))
    except Exception:
        pass
    return builders


def _fit_fold_probabilities(X, y, train_idx, test_idx) -> list[list[float]]:
    from app.services.ml_models.calibration import calibrate_fitted_model

    gap = settings.triple_barrier_horizon_sessions
    calibration_rows = max(20, int(len(train_idx) * settings.ml_calibration_fraction))
    cal_start = max(1, len(train_idx) - calibration_rows)
    base_end = max(1, cal_start - gap)
    base_idx = train_idx[:base_end]
    cal_idx = train_idx[cal_start:]
    y_base = [y[index] for index in base_idx]
    y_cal = [y[index] for index in cal_idx]
    if len(set(y_base)) < 2:
        return []
    probabilities = []
    for builder in _primary_builders():
        model = builder(y_base)
        model.fit([X[index] for index in base_idx], y_base)
        model, _ = calibrate_fitted_model(
            model, [X[index] for index in cal_idx], y_cal,
        )
        probabilities.append(model.predict_proba([X[index] for index in test_idx])[:, 1].tolist())
    return probabilities


def rebuild_oof_meta_labels(db: Session, asset_id: str) -> dict:
    """Primary side pochodzi wyłącznie z predykcji modeli, które nie widziały danego wiersza."""
    rows = list_training_rows_for_target(db, "target_triple_barrier", asset_id=asset_id)
    if len(rows) < settings.ml_min_training_rows:
        return {"asset_id": asset_id, "updated": 0, "reason": "not_enough_rows"}
    features = [json.loads(row.feature_json) for row in rows]
    feature_names = list(features[0].keys())
    X = [[float(payload.get(name, 0.0) or 0.0) for name in feature_names] for payload in features]
    y = [int(row.target_triple_barrier) for row in rows]
    groups = [ensure_utc(row.snapshot_at).date() for row in rows]
    splits = purged_group_time_series_splits(
        groups, n_splits=5, purge_sessions=settings.triple_barrier_horizon_sessions,
    )
    asset = get_asset(db, asset_id)
    if asset is None:
        return {"asset_id": asset_id, "updated": 0, "reason": "unknown_asset"}
    cost = transaction_cost_pct(market_segment(asset))
    updated = 0
    for train_idx, test_idx in splits:
        per_model = _fit_fold_probabilities(X, y, train_idx, test_idx)
        if not per_model:
            continue
        for offset, row_index in enumerate(test_idx):
            probabilities = [model_prob[offset] for model_prob in per_model]
            probability = float(mean(probabilities))
            side = 1 if probability >= 0.5 else -1
            row = rows[row_index]
            raw_return = float(row.triple_barrier_return_pct or 0.0)
            net_return = side * raw_return - cost
            row.meta_primary_probability = probability
            row.meta_primary_margin = abs(probability - 0.5) * 2.0
            row.meta_model_disagreement = float(pstdev(probabilities)) if len(probabilities) > 1 else 0.0
            row.meta_side = side
            row.meta_strategy_return_pct = round(net_return, 6)
            row.target_meta_label = int(net_return > 0 and row.triple_barrier_hit != "ambiguous")
            row.meta_label_source = "purged_oof_primary"
            updated += 1
    db.commit()
    return {"asset_id": asset_id, "updated": updated, "folds": len(splits)}


def live_primary_meta_features(db: Session, asset_id: str, vec: dict) -> dict:
    """Cechy primary dla bieżącej decyzji, z preferencją modeli per-asset."""
    from app.services.ml_models.registry import predict_proba_single

    asset = get_asset(db, asset_id)
    market = market_segment(asset) if asset is not None else "OTHER"
    stmt = select(MLModelRunORM).where(
        MLModelRunORM.target_name == "target_triple_barrier",
        MLModelRunORM.deployment_role.in_(("champion", "challenger")),
    )
    per_asset = list(db.scalars(
        stmt.where(MLModelRunORM.asset_id == asset_id)
        .order_by(MLModelRunORM.trained_at.desc()).limit(12)
    ).all())
    runs = per_asset
    if not runs:
        runs = list(db.scalars(
            stmt.where(
                MLModelRunORM.asset_id.is_(None),
                MLModelRunORM.market_segment == market,
            ).order_by(MLModelRunORM.trained_at.desc()).limit(12)
        ).all())
    latest_by_model = {}
    for run in runs:
        latest_by_model.setdefault(run.model_name, run)
    probabilities = []
    for run in latest_by_model.values():
        try:
            probabilities.append(predict_proba_single(run.model_name, run.model_path, [vec]))
        except Exception:
            continue
    probability = float(mean(probabilities)) if probabilities else 0.5
    return {
        "meta_primary_probability": probability,
        "meta_primary_margin": abs(probability - 0.5) * 2.0,
        "meta_model_disagreement": float(pstdev(probabilities)) if len(probabilities) > 1 else 0.0,
    }
