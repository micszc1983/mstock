"""Leakage-safe feature-group ablation for the enriched ML dataset."""
from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.assets import get_asset
from app.repositories.ml import list_training_rows_for_target
from app.services.point_in_time_features import FEATURE_GROUPS
from app.utils.datetime import ensure_utc


def _return_for(row, target_name: str) -> float:
    if target_name == "target_up_20d":
        return float(row.target_return_20d or 0.0)
    if target_name == "target_triple_barrier":
        return float(row.triple_barrier_return_pct or 0.0)
    return float(row.target_return_5d or 0.0)


def _evaluate(rows: list, features: list[dict], names: list[str], target_name: str, cost: float, purge: int) -> dict:
    import numpy as np
    from sklearn.metrics import accuracy_score, brier_score_loss, f1_score
    from app.services.ml_models.logistic import _build_pipeline
    from app.services.ml_validation import purged_group_time_series_splits

    X = [[float(feature.get(name, 0.0) or 0.0) for name in names] for feature in features]
    y = [int(getattr(row, target_name)) for row in rows]
    groups = [ensure_utc(row.snapshot_at).date() for row in rows]
    splits = purged_group_time_series_splits(groups, n_splits=5, purge_sessions=purge)
    predictions: list[int] = []
    probabilities: list[float] = []
    truth: list[int] = []
    net_returns: list[float] = []
    return_dates: list[object] = []
    selected_returns: list[float] = []

    for train_idx, test_idx in splits:
        y_train = [y[index] for index in train_idx]
        if len(set(y_train)) < 2:
            continue
        model = _build_pipeline()
        model.fit([X[index] for index in train_idx], y_train)
        fold_x = [X[index] for index in test_idx]
        fold_predictions = [int(value) for value in model.predict(fold_x)]
        fold_probabilities = [float(value) for value in model.predict_proba(fold_x)[:, 1]]
        for index, prediction, probability in zip(test_idx, fold_predictions, fold_probabilities):
            row = rows[index]
            if target_name == "target_meta_label":
                value = float(row.meta_strategy_return_pct or 0.0) if prediction == 1 else 0.0
                selected = prediction == 1
            else:
                raw = _return_for(row, target_name)
                value = (raw if prediction == 1 else -raw) - cost
                selected = True
            net_returns.append(value)
            return_dates.append(groups[index])
            if selected:
                selected_returns.append(value)
            predictions.append(prediction)
            probabilities.append(probability)
            truth.append(y[index])

    if not truth:
        return {}
    values = np.asarray(net_returns, dtype=float)
    selected = np.asarray(selected_returns, dtype=float)
    wins = selected[selected > 0]
    losses = selected[selected < 0]
    # Market runs contain simultaneous rows for many assets. Build drawdown from
    # the equal-weight daily portfolio instead of pretending every row is a
    # sequential all-in trade.
    daily_returns: dict[object, list[float]] = defaultdict(list)
    for day, value in zip(return_dates, net_returns):
        daily_returns[day].append(value)
    portfolio_returns = np.asarray([
        mean(daily_returns[day]) for day in sorted(daily_returns)
    ], dtype=float)
    equity = np.cumprod(1.0 + portfolio_returns / 100.0)
    peaks = np.maximum.accumulate(equity)
    drawdown = (equity / peaks - 1.0) * 100.0
    return {
        "rows": len(truth),
        "features": len(names),
        "cv_folds": len(splits),
        "accuracy": round(float(accuracy_score(truth, predictions)), 6),
        "f1": round(float(f1_score(truth, predictions, zero_division=0)), 6),
        "brier": round(float(brier_score_loss(truth, probabilities)), 6),
        "coverage_pct": round(len(selected_returns) / len(truth) * 100.0, 4),
        "avg_net_return_pct": round(float(mean(net_returns)), 6),
        "avg_selected_net_return_pct": round(float(mean(selected_returns)), 6) if selected_returns else 0.0,
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 6) if len(losses) and losses.sum() else None,
        "max_drawdown_pct": round(float(abs(drawdown.min())), 6),
    }


def run_feature_ablation(
    db: Session, *, target_name: str = "target_up_5d",
    asset_id: str | None = None, market: str | None = None,
    approve: bool = False,
) -> dict:
    """Compare additions with identical purged folds and a fixed LR estimator."""
    if asset_id is None and market not in {"GPW", "USA"}:
        raise ValueError("Podaj asset_id albo market=GPW/USA")
    rows = list_training_rows_for_target(
        db, target_name, asset_id=asset_id, market_segment=market,
    )
    if target_name == "target_meta_label":
        from app.services.meta_labeling import enrich_meta_features
        rows = [
            row for row in rows
            if row.meta_label_source == "purged_oof_primary"
            and row.meta_primary_probability is not None
        ]
        features = [enrich_meta_features(json.loads(row.feature_json), row=row) for row in rows]
    else:
        features = [json.loads(row.feature_json) for row in rows]
    if len(rows) < settings.ml_min_training_rows:
        raise ValueError(f"Za mało danych do ablation: {len(rows)}")

    enriched = {name for names in FEATURE_GROUPS.values() for name in names}
    available_names = list(features[0])
    if not enriched.intersection(available_names):
        raise ValueError("Dataset nie zawiera nowych cech; najpierw przebuduj /ml/dataset/build")
    baseline = [name for name in available_names if name not in enriched]
    scenarios = {
        "baseline": baseline,
        "+availability": baseline + FEATURE_GROUPS["availability"],
        "+earnings": baseline + FEATURE_GROUPS["availability"] + FEATURE_GROUPS["earnings"],
        "+insider_short": baseline + FEATURE_GROUPS["availability"] + FEATURE_GROUPS["insider_short"],
        "+event_news": baseline + FEATURE_GROUPS["availability"] + FEATURE_GROUPS["event_news"],
        "+all": baseline + [name for group in FEATURE_GROUPS.values() for name in group],
    }
    horizon_gap = 20 if target_name == "target_up_20d" else (
        settings.triple_barrier_horizon_sessions
        if target_name in {"target_triple_barrier", "target_meta_label"} else 5
    )
    from app.services.recommendation_calibration import market_segment, transaction_cost_pct
    asset = get_asset(db, asset_id) if asset_id else None
    resolved_market = market_segment(asset) if asset is not None else market or "OTHER"
    cost = transaction_cost_pct(resolved_market)
    results = {
        name: _evaluate(rows, features, feature_names, target_name, cost, horizon_gap)
        for name, feature_names in scenarios.items()
    }
    base = results["baseline"]
    for result in results.values():
        if result and base:
            result["delta_f1"] = round(result["f1"] - base["f1"], 6)
            result["delta_avg_net_return_pct"] = round(
                result["avg_net_return_pct"] - base["avg_net_return_pct"], 6
            )
    scenario_for_group = {
        "availability": "+availability", "earnings": "+earnings",
        "insider_short": "+insider_short", "event_news": "+event_news",
    }
    approved_groups = []
    for group, scenario in scenario_for_group.items():
        result = results[scenario]
        if (
            result
            and result["delta_f1"] > 0
            and result["delta_avg_net_return_pct"] > 0
            and result["brier"] <= base["brier"]
        ):
            approved_groups.append(group)
    if approve:
        from app.repositories.ml import upsert_setting
        upsert_setting(
            db, _selection_key(target_name, asset_id, resolved_market),
            json.dumps(approved_groups),
        )
        db.commit()
    return {
        "target_name": target_name, "asset_id": asset_id, "market": resolved_market,
        "model": "logistic_regression", "validation": "purged_group_time_series",
        "transaction_cost_pct": cost, "results": results,
        "approved_groups": approved_groups,
        "selection_saved": approve,
    }


def _selection_key(target_name: str, asset_id: str | None, market: str) -> str:
    scope = f"asset:{asset_id}" if asset_id else f"market:{market}"
    return f"ml_feature_groups:{target_name}:{scope}"


def approved_feature_names_for_training(
    db: Session, available_names: list[str], *, target_name: str,
    asset_id: str | None, market: str | None,
) -> list[str]:
    """Return baseline + only feature groups explicitly accepted by ablation."""
    from app.repositories.ml import get_setting
    from app.services.recommendation_calibration import market_segment

    resolved_market = market
    if asset_id is not None:
        asset = get_asset(db, asset_id)
        resolved_market = market_segment(asset) if asset is not None else "OTHER"
    resolved_market = resolved_market or "OTHER"
    exact = get_setting(db, _selection_key(target_name, asset_id, resolved_market))
    fallback = (
        get_setting(db, _selection_key(target_name, None, resolved_market))
        if asset_id is not None and exact is None else None
    )
    setting = exact or fallback
    try:
        approved = set(json.loads(setting.setting_value)) if setting is not None else set()
    except (TypeError, ValueError, json.JSONDecodeError):
        approved = set()
    enriched = {name for names in FEATURE_GROUPS.values() for name in names}
    selected = [name for name in available_names if name not in enriched]
    for group in FEATURE_GROUPS:
        if group in approved:
            selected.extend(name for name in FEATURE_GROUPS[group] if name in available_names)
    return list(dict.fromkeys(selected))
