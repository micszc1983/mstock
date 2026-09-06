"""Ścisły audyt walk-forward kalibracji rekomendacji.

Każdy fold używa wyłącznie danych sprzed 20-sesyjnego embargo. Kalibrator,
progi i winsoryzacja powstają na części treningowej, nigdy na bloku testowym.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    AssetORM,
    DailyAssetFeatureORM,
    MLTrainingRowORM,
    RecommendationAuditRunORM,
)
from app.services.recommendation_calibration import (
    BUY_CLASS,
    CALIBRATION_MODEL_VERSION,
    NO_TRADE_CLASS,
    SELL_CLASS,
    _apply_calibration,
    _fit_probability_calibrator,
    _model_pipeline,
    _probability_matrix,
    _select_calibrated_action,
    _tune_threshold,
    _vector,
    transaction_cost_pct,
)


AUDIT_MODEL_VERSION = CALIBRATION_MODEL_VERSION
EMBARGO_SESSIONS = 20
DEFAULT_FOLDS = 3


@dataclass(frozen=True)
class AuditSample:
    asset_id: str
    snapshot_at: datetime
    market: str
    regime: str
    vector: list[float]
    payload: dict
    label: int
    return_5d: float
    cost: float
    outlier_reason: str | None


@dataclass
class AuditSegmentModel:
    model: object
    calibrators: dict[int, object | None]
    lower: object
    upper: object
    buy: object
    sell: object
    scope: str
    sample_size: int


def _row_market(asset_type: str, currency: str, symbol: str | None) -> str:
    if asset_type != "stock":
        return "OTHER"
    return "GPW" if currency == "PLN" or (symbol or "").upper().endswith(".WA") else "USA"


def _outlier_reason(payload: dict, r1: float | None, r5: float, r20: float | None) -> str | None:
    if r1 is not None and abs(r1) > 35:
        return "possible_corporate_action_1d"
    if abs(r5) > 60:
        return "possible_corporate_action_5d"
    if r20 is not None and abs(r20) > 100:
        return "possible_corporate_action_20d"
    for key, limit in (("price_change_1d_pct", 35), ("price_change_5d_pct", 60), ("price_change_20d_pct", 100)):
        try:
            if abs(float(payload.get(key, 0) or 0)) > limit:
                return f"feature_jump_{key}"
        except (TypeError, ValueError):
            continue
    return None


def load_audit_samples(db: Session) -> list[AuditSample]:
    latest_feature_per_day = (
        select(
            DailyAssetFeatureORM.asset_id.label("asset_id"),
            func.date(DailyAssetFeatureORM.snapshot_at).label("snapshot_day"),
            func.max(DailyAssetFeatureORM.id).label("feature_id"),
        )
        .group_by(DailyAssetFeatureORM.asset_id, func.date(DailyAssetFeatureORM.snapshot_at))
        .subquery()
    )
    rows = db.execute(
        select(
            MLTrainingRowORM.asset_id,
            MLTrainingRowORM.snapshot_at,
            MLTrainingRowORM.feature_json,
            MLTrainingRowORM.target_return_1d,
            MLTrainingRowORM.target_return_5d,
            MLTrainingRowORM.target_return_20d,
            AssetORM.type,
            AssetORM.currency,
            AssetORM.price_symbol,
            DailyAssetFeatureORM.regime_label,
        )
        .join(AssetORM, AssetORM.id == MLTrainingRowORM.asset_id)
        .join(
            latest_feature_per_day,
            and_(
                latest_feature_per_day.c.asset_id == MLTrainingRowORM.asset_id,
                latest_feature_per_day.c.snapshot_day == func.date(MLTrainingRowORM.snapshot_at),
            ),
        )
        .join(DailyAssetFeatureORM, DailyAssetFeatureORM.id == latest_feature_per_day.c.feature_id)
        .where(MLTrainingRowORM.target_return_5d.isnot(None))
        .order_by(MLTrainingRowORM.snapshot_at.asc(), MLTrainingRowORM.asset_id.asc())
    ).all()
    result: list[AuditSample] = []
    for asset_id, snap, raw_json, r1, r5, r20, asset_type, currency, symbol, regime in rows:
        try:
            payload = json.loads(raw_json)
            realized = float(r5)
            market = _row_market(asset_type, currency, symbol)
            cost = transaction_cost_pct(market)
            label = BUY_CLASS if realized > cost else SELL_CLASS if realized < -cost else NO_TRADE_CLASS
            result.append(AuditSample(
                asset_id=asset_id,
                snapshot_at=snap,
                market=market,
                regime=regime,
                vector=_vector(payload),
                payload=payload,
                label=label,
                return_5d=realized,
                cost=cost,
                outlier_reason=_outlier_reason(payload, float(r1) if r1 is not None else None, realized, float(r20) if r20 is not None else None),
            ))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def _clip(matrix, lower, upper):
    import numpy as np
    return np.minimum(np.maximum(matrix, lower), upper)


def _fit_segment(samples: list[AuditSample], scope: str) -> AuditSegmentModel | None:
    import numpy as np

    minimum = settings.recommendation_calibration_min_rows
    if len(samples) < minimum:
        return None
    samples = sorted(samples, key=lambda row: row.snapshot_at)[-settings.recommendation_calibration_max_rows:]
    X = np.asarray([row.vector for row in samples], dtype=float)
    y = np.asarray([row.label for row in samples], dtype=int)
    returns = np.asarray([row.return_5d for row in samples], dtype=float)
    costs = np.asarray([row.cost for row in samples], dtype=float)
    if len(set(y.tolist())) < 2:
        return None

    # Granice są liczone wyłącznie na treningu. Chronią model przed pojedynczymi
    # błędami danych, nie zmieniając źródłowych świec ani dziennika jakości.
    lower = np.quantile(X, 0.01, axis=0)
    upper = np.quantile(X, 0.99, axis=0)
    X = _clip(X, lower, upper)
    first = max(30, int(len(samples) * 0.60))
    second = max(first + 20, int(len(samples) * 0.80))
    if len(samples) - second < 20 or len(set(y[:first].tolist())) < 2:
        return None

    base = _model_pipeline()
    base.fit(X[:first], y[:first])
    raw_cal = _probability_matrix(base, X[first:second])
    calibrators: dict[int, object | None] = {}
    for column, label in enumerate((SELL_CLASS, NO_TRADE_CLASS, BUY_CLASS)):
        binary = (y[first:second] == label).astype(float)
        calibrators[label] = _fit_probability_calibrator(raw_cal[:, column], binary)
    tuned = _apply_calibration(_probability_matrix(base, X[second:]), calibrators)
    buy = _tune_threshold(tuned[:, 2], returns[second:], costs[second:], BUY_CLASS)
    sell = _tune_threshold(tuned[:, 0], returns[second:], costs[second:], SELL_CLASS)

    final = _model_pipeline()
    final.fit(X, y)
    return AuditSegmentModel(final, calibrators, lower, upper, buy, sell, scope, len(samples))


def _predict(model: AuditSegmentModel, sample: AuditSample) -> tuple[int, list[float]]:
    import numpy as np

    matrix = _clip(np.asarray([sample.vector], dtype=float), model.lower, model.upper)
    p_sell, p_no_trade, p_buy = _apply_calibration(
        _probability_matrix(model.model, matrix), model.calibrators
    )[0]
    action = _select_calibrated_action(
        float(p_sell),
        float(p_no_trade),
        float(p_buy),
        model.buy,
        model.sell,
    )
    return action, [float(p_sell), float(p_no_trade), float(p_buy)]


def _legacy_action(payload: dict) -> int:
    def val(name: str) -> float:
        try:
            return float(payload.get(name, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    signal = (
        max(-1.0, min(1.0, val("trend_score") / 100.0)) * 0.30
        + max(-1.0, min(1.0, val("sentiment_score") / 100.0)) * 0.15
        + max(-1.0, min(1.0, val("momentum_20d") / 15.0)) * 0.20
        + max(-1.0, min(1.0, (50.0 - val("fragility_score")) / 50.0)) * 0.20
        + max(-1.0, min(1.0, (50.0 - val("divergence_score")) / 50.0)) * 0.15
    )
    score = 50.0 + signal * 50.0
    return BUY_CLASS if score >= 62 else SELL_CLASS if score <= 38 else NO_TRADE_CLASS


def _net_return(action: int, sample: AuditSample) -> float:
    if action == BUY_CLASS:
        return sample.return_5d - sample.cost
    if action == SELL_CLASS:
        return -sample.return_5d - sample.cost
    return 0.0


def _strategy_metrics(rows: list[dict], key: str) -> dict:
    import numpy as np

    actions = np.asarray([row[f"{key}_action"] for row in rows], dtype=int)
    net = np.asarray([row[f"{key}_net"] for row in rows], dtype=float)
    trade_mask = actions != NO_TRADE_CLASS
    trades = net[trade_mask]
    wins = trades[trades > 0]
    losses = trades[trades < 0]

    by_day: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(float(row[f"{key}_net"]))
    period_returns = np.asarray([np.mean(by_day[day]) for day in sorted(by_day)], dtype=float) / 100.0
    equity = np.cumprod(1.0 + period_returns) if len(period_returns) else np.asarray([1.0])
    peaks = np.maximum.accumulate(equity)
    drawdown = (equity / peaks - 1.0) * 100.0
    std = float(np.std(period_returns, ddof=1)) if len(period_returns) > 1 else 0.0
    downside = period_returns[period_returns < 0]
    downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    annualizer = math.sqrt(252.0 / 5.0)
    mean_period = float(np.mean(period_returns)) if len(period_returns) else 0.0
    return {
        "signals": len(rows),
        "trades": int(trade_mask.sum()),
        "coverage_pct": round(float(trade_mask.mean() * 100), 3) if len(rows) else 0.0,
        "no_trade_pct": round(float((~trade_mask).mean() * 100), 3) if len(rows) else 0.0,
        "win_rate_pct": round(float((trades > 0).mean() * 100), 3) if len(trades) else 0.0,
        "avg_net_return_pct": round(float(np.mean(trades)), 6) if len(trades) else 0.0,
        "median_net_return_pct": round(float(np.median(trades)), 6) if len(trades) else 0.0,
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4) if len(losses) and losses.sum() else None,
        "portfolio_return_pct": round(float((equity[-1] - 1.0) * 100.0), 4),
        "max_drawdown_pct": round(float(abs(drawdown.min())), 4) if len(drawdown) else 0.0,
        "sharpe": round(mean_period / std * annualizer, 4) if std > 0 else None,
        "sortino": round(mean_period / downside_std * annualizer, 4) if downside_std > 0 else None,
    }


def _calibration_metrics(rows: list[dict]) -> dict:
    import numpy as np

    probs = np.asarray([row["probabilities"] for row in rows], dtype=float)
    labels = np.asarray([{-1: 0, 0: 1, 1: 2}[row["label"]] for row in rows], dtype=int)
    one_hot = np.eye(3)[labels]
    chosen = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    correct = (chosen == labels).astype(float)
    ece = 0.0
    bins = []
    for low in np.arange(0.0, 1.0, 0.1):
        high = low + 0.1
        mask = (confidence >= low) & (confidence < high if high < 1.0 else confidence <= high)
        if not mask.any():
            continue
        acc = float(correct[mask].mean())
        conf = float(confidence[mask].mean())
        ece += float(mask.mean()) * abs(acc - conf)
        bins.append({"from": round(float(low), 1), "to": round(float(high), 1), "count": int(mask.sum()), "accuracy": round(acc, 4), "confidence": round(conf, 4)})
    selected_actions = np.asarray([row["calibrated_action"] for row in rows], dtype=int)
    trade_mask = selected_actions != NO_TRADE_CLASS
    return {
        "multiclass_brier": round(float(np.mean(np.sum((probs - one_hot) ** 2, axis=1))), 6),
        "log_loss": round(float(-np.mean(np.log(np.clip(probs[np.arange(len(labels)), labels], 1e-12, 1.0)))), 6),
        "ece": round(ece, 6),
        "class_accuracy_pct": round(float((selected_actions == np.asarray([r["label"] for r in rows])).mean() * 100), 3),
        "trade_direction_accuracy_pct": round(float((selected_actions[trade_mask] == np.asarray([r["label"] for r in rows])[trade_mask]).mean() * 100), 3) if trade_mask.any() else 0.0,
        "bins": bins,
    }


def _breakdown(rows: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    result = []
    for name, subset in sorted(groups.items()):
        metrics = _strategy_metrics(subset, "calibrated")
        result.append({"name": name, **metrics})
    return result


def _side_breakdown(rows: list[dict], field: str) -> list[dict]:
    result = []
    for name in sorted({str(row[field]) for row in rows}):
        for action, side in ((BUY_CLASS, "BUY"), (SELL_CLASS, "SELL")):
            subset = [
                row for row in rows
                if str(row[field]) == name and row["calibrated_action"] == action
            ]
            metrics = _strategy_metrics(subset, "calibrated")
            result.append({"name": name, "side": side, **metrics})
    return result


def run_walk_forward_audit(db: Session, fold_count: int = DEFAULT_FOLDS) -> dict:
    all_samples = load_audit_samples(db)
    excluded = [row for row in all_samples if row.outlier_reason]
    samples = [row for row in all_samples if not row.outlier_reason]
    dates = sorted({row.snapshot_at.date() for row in samples})
    fold_count = min(max(int(fold_count), 2), 5)
    minimum_dates = 120 + EMBARGO_SESSIONS + fold_count * 20
    if len(dates) < minimum_dates:
        raise ValueError(f"Za mało sesji do walk-forward: {len(dates)}; wymagane co najmniej {minimum_dates}.")

    initial_train = max(120, int(len(dates) * 0.50))
    available = len(dates) - initial_train - EMBARGO_SESSIONS
    block = available // fold_count
    if block < 20:
        raise ValueError("Bloki testowe walk-forward miałyby mniej niż 20 sesji.")

    evaluated: list[dict] = []
    fold_summaries = []
    for fold in range(fold_count):
        test_start_idx = initial_train + EMBARGO_SESSIONS + fold * block
        test_end_idx = len(dates) if fold == fold_count - 1 else test_start_idx + block
        train_end_idx = test_start_idx - EMBARGO_SESSIONS
        train_end = dates[train_end_idx]
        test_start = dates[test_start_idx]
        test_end = dates[test_end_idx - 1]
        train = [row for row in samples if row.snapshot_at.date() < train_end]
        test = [row for row in samples if test_start <= row.snapshot_at.date() <= test_end]

        segment_cache: dict[tuple[str | None, str | None], AuditSegmentModel | None] = {}

        def model_for(market: str | None, regime: str | None, scope: str):
            key = (market, regime)
            if key not in segment_cache:
                subset = [row for row in train if (market is None or row.market == market) and (regime is None or row.regime == regime)]
                segment_cache[key] = _fit_segment(subset, scope)
            return segment_cache[key]

        fold_rows = 0
        scopes: dict[str, int] = defaultdict(int)
        for sample in test:
            candidates = (
                (sample.market, sample.regime, "market_regime"),
                (sample.market, None, "market"),
                (None, sample.regime, "regime"),
                (None, None, "global"),
            )
            model = None
            for market, regime, scope in candidates:
                model = model_for(market, regime, scope)
                if model is not None:
                    break
            if model is None:
                continue
            action, probabilities = _predict(model, sample)
            legacy_action = _legacy_action(sample.payload)
            scopes[model.scope] += 1
            evaluated.append({
                "date": sample.snapshot_at.date().isoformat(),
                "market": sample.market,
                "regime": sample.regime,
                "label": sample.label,
                "probabilities": probabilities,
                "calibrated_action": action,
                "calibrated_net": _net_return(action, sample),
                "legacy_action": legacy_action,
                "legacy_net": _net_return(legacy_action, sample),
                "buy_hold_action": BUY_CLASS,
                "buy_hold_net": sample.return_5d,
                "always_flat_action": NO_TRADE_CLASS,
                "always_flat_net": 0.0,
            })
            fold_rows += 1
        fold_summaries.append({
            "fold": fold + 1,
            "train_end_exclusive": train_end.isoformat(),
            "test_start": test_start.isoformat(),
            "test_end": test_end.isoformat(),
            "train_rows": len(train),
            "test_rows": fold_rows,
            "embargo_sessions": EMBARGO_SESSIONS,
            "scopes": dict(scopes),
        })

    if not evaluated:
        raise ValueError("Żaden fold nie utworzył wiarygodnego modelu segmentu.")
    result = {
        "model_version": AUDIT_MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_rows": len(all_samples),
        "eligible_rows": len(samples),
        "evaluated_rows": len(evaluated),
        "excluded_outliers": len(excluded),
        "outlier_reasons": dict(sorted({reason: sum(1 for row in excluded if row.outlier_reason == reason) for reason in {row.outlier_reason for row in excluded}}.items())),
        "fold_count": fold_count,
        "embargo_sessions": EMBARGO_SESSIONS,
        "horizon_sessions": 5,
        "folds": fold_summaries,
        "strategies": {
            "calibrated": _strategy_metrics(evaluated, "calibrated"),
            "legacy_feature_rule": _strategy_metrics(evaluated, "legacy"),
            "buy_hold": _strategy_metrics(evaluated, "buy_hold"),
            "always_flat": _strategy_metrics(evaluated, "always_flat"),
        },
        "calibration": _calibration_metrics(evaluated),
        "by_market": _breakdown(evaluated, "market"),
        "by_regime": _breakdown(evaluated, "regime"),
        "by_market_side": _side_breakdown(evaluated, "market"),
        "by_regime_side": _side_breakdown(evaluated, "regime"),
        "notes": [
            "Testy są chronologiczne; pomiędzy treningiem i testem pozostaje 20 sesji embargo.",
            "Koszt jest odejmowany od każdej decyzji BUY/SELL; NO_TRADE ma zwrot 0.",
            "Bramka live wymaga osobnego potwierdzenia przewagi dla strony BUY lub SELL, zarówno dla rynku, jak i reżimu.",
            "legacy_feature_rule jest odtwarzalnym przybliżeniem starej reguły 62/38 na cechach historycznych.",
            "Portfolio return agreguje średni 5-sesyjny wynik wszystkich aktywów danego dnia; okna częściowo się nakładają.",
            "Podejrzane skoki cen są raportowane i wyłączane z treningu, bez modyfikacji źródłowego OHLCV.",
        ],
    }
    run = RecommendationAuditRunORM(
        created_at=datetime.now(timezone.utc),
        model_version=AUDIT_MODEL_VERSION,
        dataset_rows=len(all_samples),
        eligible_rows=len(samples),
        excluded_outliers=len(excluded),
        fold_count=fold_count,
        embargo_sessions=EMBARGO_SESSIONS,
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    result["id"] = run.id
    return result


def latest_audit(db: Session) -> dict | None:
    row = db.scalar(
        select(RecommendationAuditRunORM)
        .order_by(RecommendationAuditRunORM.created_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    result = json.loads(row.result_json)
    result["id"] = row.id
    return result


def automatic_audit_status(
    db: Session,
    now: datetime | None = None,
    interval_days: int | None = None,
    min_new_outcomes: int | None = None,
) -> dict:
    """Return whether enough time and genuinely new 5d samples justify an audit."""
    current_time = now or datetime.now(timezone.utc)
    interval = max(1, int(
        interval_days if interval_days is not None else settings.recommendation_audit_interval_days
    ))
    minimum_new = max(1, int(
        min_new_outcomes
        if min_new_outcomes is not None
        else settings.recommendation_audit_min_new_outcomes
    ))
    latest = db.scalar(
        select(RecommendationAuditRunORM)
        .where(RecommendationAuditRunORM.model_version == AUDIT_MODEL_VERSION)
        .order_by(RecommendationAuditRunORM.created_at.desc())
        .limit(1)
    )
    if latest is not None:
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = current_time - created_at
        if age < timedelta(days=interval):
            return {
                "due": False,
                "reason": "interval_not_elapsed",
                "last_audit_at": created_at,
                "age_days": round(age.total_seconds() / 86400, 2),
                "new_outcomes": 0,
                "required_new_outcomes": minimum_new,
            }

    samples = load_audit_samples(db)
    eligible = [sample for sample in samples if sample.outlier_reason is None]
    eligible_rows = len(eligible)
    last_test_date = None
    if latest is not None:
        try:
            payload = json.loads(latest.result_json)
            test_ends = [
                datetime.fromisoformat(str(fold["test_end"])).date()
                for fold in payload.get("folds", [])
                if fold.get("test_end")
            ]
            if test_ends:
                last_test_date = max(test_ends)
        except (TypeError, ValueError, json.JSONDecodeError):
            last_test_date = None
        if last_test_date is None:
            last_test_date = latest.created_at.date()
    new_outcomes = (
        sum(sample.snapshot_at.date() > last_test_date for sample in eligible)
        if last_test_date is not None
        else eligible_rows
    )
    if new_outcomes < minimum_new:
        return {
            "due": False,
            "reason": "not_enough_new_outcomes",
            "last_audit_at": latest.created_at if latest is not None else None,
            "eligible_rows": eligible_rows,
            "last_test_date": last_test_date,
            "new_outcomes": new_outcomes,
            "required_new_outcomes": minimum_new,
        }
    return {
        "due": True,
        "reason": "ready",
        "last_audit_at": latest.created_at if latest is not None else None,
        "eligible_rows": eligible_rows,
        "last_test_date": last_test_date,
        "new_outcomes": new_outcomes,
        "required_new_outcomes": minimum_new,
    }


def run_automatic_audit_if_due(db: Session, now: datetime | None = None) -> dict:
    if not settings.recommendation_audit_auto_enabled:
        return {"ran": False, "due": False, "reason": "disabled"}
    status = automatic_audit_status(db, now=now)
    if not status["due"]:
        return {"ran": False, **status}
    report = run_walk_forward_audit(
        db,
        fold_count=max(2, min(5, int(settings.recommendation_audit_folds))),
    )
    from app.services.recommendation_engine import invalidate_recommendations_cache
    invalidate_recommendations_cache()
    return {
        "ran": True,
        **status,
        "audit_id": report["id"],
        "evaluated_rows": report["evaluated_rows"],
        "eligible_rows": report["eligible_rows"],
    }
