"""Historyczna kalibracja decyzji tradingowych GPW/USA i reżimów rynku."""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AssetORM, DailyAssetFeatureORM, MLTrainingRowORM
from app.services.ml_validation import purged_group_time_series_splits
from app.utils.datetime import ensure_utc


FEATURE_NAMES = (
    "trend_score", "sentiment_score", "divergence_score", "fragility_score",
    "narrative_shift_score", "volatility_10d", "momentum_20d",
    "price_change_1d_pct", "price_change_5d_pct", "price_change_20d_pct",
    "rsi_14", "macd_histogram", "above_sma200", "bb_pct", "volume_ratio_20d",
    "alpha_vs_spy_5d", "spy_return_5d", "sector_return_5d", "sector_vs_spy_5d",
    "rs_vs_sector_20d", "vix_level", "vix_change_5d", "dxy_return_5d",
    "treasury_10y", "iv_rank", "days_to_earnings", "poc_distance_pct",
)

BUY_CLASS = 1
NO_TRADE_CLASS = 0
SELL_CLASS = -1


@dataclass(frozen=True)
class ThresholdStats:
    threshold: float
    selected: int
    expected_gross_pct: float
    expected_net_pct: float
    uncertainty_pct: float


@dataclass
class SegmentModel:
    model: object
    calibrators: dict[int, object | None]
    market: str
    regime: str
    scope: str
    sample_size: int
    buy: ThresholdStats
    sell: ThresholdStats


@dataclass(frozen=True)
class CalibratedDecision:
    action: str
    confidence_probability: float
    probability_buy: float
    probability_sell: float
    probability_no_trade: float
    market: str
    regime: str
    scope: str
    sample_size: int
    buy_threshold: float
    sell_threshold: float
    transaction_cost_pct: float
    expected_gross_edge_pct: float
    expected_net_edge_pct: float
    uncertainty_pct: float
    no_trade_reason: str | None


_cache: dict[tuple[str, str, str], tuple[str, SegmentModel | None]] = {}
_cache_lock = threading.Lock()


def _calibration_session(market: str | None, at: datetime | None = None) -> str:
    """Stable cache generation for one local market day.

    Rebuilding the model every hour caused thresholds to oscillate intraday.
    A market-local date keeps the fitted calibration frozen for the session,
    while still rotating it automatically on the next trading day.
    """
    moment = ensure_utc(at or datetime.now(timezone.utc))
    timezone_name = "Europe/Warsaw" if market == "GPW" else "America/New_York" if market == "USA" else "UTC"
    return moment.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def market_segment(asset: AssetORM) -> str:
    if asset.type != "stock":
        return "OTHER"
    symbol = (asset.price_symbol or asset.symbol or "").upper()
    return "GPW" if asset.currency == "PLN" or symbol.endswith(".WA") else "USA"


def transaction_cost_pct(market: str) -> float:
    if market == "GPW":
        return settings.recommendation_cost_gpw_pct
    if market == "USA":
        return settings.recommendation_cost_usa_pct
    return settings.recommendation_cost_other_pct


def _vector(payload: dict) -> list[float]:
    values: list[float] = []
    for name in FEATURE_NAMES:
        try:
            value = float(payload.get(name, 0.0) or 0.0)
            values.append(value if math.isfinite(value) else 0.0)
        except (TypeError, ValueError):
            values.append(0.0)
    return values


def _market_filter(market: str):
    symbol = func.upper(func.coalesce(AssetORM.price_symbol, AssetORM.symbol, ""))
    if market == "GPW":
        return and_(AssetORM.type == "stock", or_(AssetORM.currency == "PLN", symbol.endswith(".WA")))
    if market == "USA":
        return and_(AssetORM.type == "stock", AssetORM.currency != "PLN", ~symbol.endswith(".WA"))
    return AssetORM.type != "stock"


def _load_samples(db: Session, market: str | None, regime: str | None):
    # W starszych bazach może istnieć kilka feature snapshotów z tego samego
    # dnia. Do jednego targetu ML dołączamy wyłącznie najnowszy z nich.
    latest_feature_per_day = (
        select(
            DailyAssetFeatureORM.asset_id.label("asset_id"),
            func.date(DailyAssetFeatureORM.snapshot_at).label("snapshot_day"),
            func.max(DailyAssetFeatureORM.id).label("feature_id"),
        )
        .group_by(DailyAssetFeatureORM.asset_id, func.date(DailyAssetFeatureORM.snapshot_at))
        .subquery()
    )
    stmt = (
        select(
            MLTrainingRowORM.feature_json,
            MLTrainingRowORM.target_return_5d,
            MLTrainingRowORM.snapshot_at,
            AssetORM.type,
            AssetORM.currency,
            AssetORM.price_symbol,
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
    )
    if market is not None:
        stmt = stmt.where(_market_filter(market))
    if regime is not None:
        stmt = stmt.where(DailyAssetFeatureORM.regime_label == regime)
    # The secondary keys are required: a snapshot normally contains many
    # assets with exactly the same timestamp. Without them LIMIT could select
    # a different boundary row on every refresh, changing the fitted model.
    stmt = stmt.order_by(
        MLTrainingRowORM.snapshot_at.desc(),
        MLTrainingRowORM.asset_id.desc(),
        MLTrainingRowORM.id.desc(),
    ).limit(
        settings.recommendation_calibration_max_rows
    )
    rows = list(reversed(db.execute(stmt).all()))

    samples = []
    for feature_json, realized_return, snapshot_at, asset_type, currency, price_symbol in rows:
        try:
            payload = json.loads(feature_json)
            row_market = (
                "OTHER" if asset_type != "stock"
                else "GPW" if currency == "PLN" or (price_symbol or "").upper().endswith(".WA")
                else "USA"
            )
            cost = transaction_cost_pct(row_market)
            realized = float(realized_return)
            label = BUY_CLASS if realized > cost else SELL_CLASS if realized < -cost else NO_TRADE_CLASS
            samples.append((_vector(payload), label, realized, cost, snapshot_at))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return samples


def _probability_matrix(model, matrix):
    import numpy as np

    raw = model.predict_proba(matrix)
    result = np.zeros((len(matrix), 3), dtype=float)
    class_to_column = {SELL_CLASS: 0, NO_TRADE_CLASS: 1, BUY_CLASS: 2}
    for source_column, label in enumerate(model.classes_):
        result[:, class_to_column[int(label)]] = raw[:, source_column]
    return result


def _apply_calibration(raw, calibrators):
    import numpy as np

    calibrated = np.zeros_like(raw, dtype=float)
    for column, label in enumerate((SELL_CLASS, NO_TRADE_CLASS, BUY_CLASS)):
        calibrator = calibrators.get(label)
        calibrated[:, column] = calibrator.predict(raw[:, column]) if calibrator is not None else raw[:, column]
    totals = calibrated.sum(axis=1, keepdims=True)
    return np.divide(calibrated, totals, out=raw.copy(), where=totals > 0)


def _tune_threshold(probabilities, returns, costs, direction: int) -> ThresholdStats:
    """Wybiera próg o najwyższej dolnej granicy przewagi netto."""
    import numpy as np

    probabilities = np.asarray(probabilities, dtype=float)
    returns = np.asarray(returns, dtype=float)
    costs = np.asarray(costs, dtype=float)
    directional_gross = returns if direction == BUY_CLASS else -returns
    minimum_selected = max(10, int(len(returns) * 0.04))
    best: ThresholdStats | None = None
    best_lower_bound = float("-inf")

    for threshold in np.arange(0.40, 0.81, 0.025):
        mask = probabilities >= threshold
        selected = int(mask.sum())
        if selected < minimum_selected:
            continue
        gross = directional_gross[mask]
        net = gross - costs[mask]
        uncertainty = 1.645 * float(np.std(net, ddof=1)) / math.sqrt(selected) if selected > 1 else float("inf")
        mean_gross = float(np.mean(gross))
        mean_net = float(np.mean(net))
        lower_bound = mean_net - uncertainty
        if lower_bound > best_lower_bound:
            best_lower_bound = lower_bound
            best = ThresholdStats(round(float(threshold), 3), selected, mean_gross, mean_net, uncertainty)

    if best is None or best_lower_bound <= 0:
        return ThresholdStats(1.01, 0, 0.0, 0.0, 0.0)
    return best


def _fit_segment(db: Session, market: str | None, regime: str | None, scope: str) -> SegmentModel | None:
    import numpy as np
    from sklearn.impute import SimpleImputer
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    samples = _load_samples(db, market, regime)
    if len(samples) < settings.recommendation_calibration_min_rows:
        return None
    X = np.asarray([row[0] for row in samples], dtype=float)
    y = np.asarray([row[1] for row in samples], dtype=int)
    returns = np.asarray([row[2] for row in samples], dtype=float)
    costs = np.asarray([row[3] for row in samples], dtype=float)
    if len(set(y.tolist())) < 2:
        return None

    def pipeline():
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=400, class_weight="balanced", random_state=42),
        )

    split_count = 4 if len(samples) >= 400 else 3
    session_groups = [ensure_utc(row[4]).date().isoformat() for row in samples]
    splits = purged_group_time_series_splits(
        session_groups,
        n_splits=split_count,
        purge_sessions=settings.recommendation_calibration_purge_sessions,
        min_train_sessions=settings.recommendation_calibration_min_train_sessions,
    )
    oof_probabilities, oof_y, oof_returns, oof_costs = [], [], [], []
    for train_idx, test_idx in splits:
        train_idx = np.asarray(train_idx, dtype=int)
        test_idx = np.asarray(test_idx, dtype=int)
        if len(set(y[train_idx].tolist())) < 2:
            continue
        fold_model = pipeline()
        fold_model.fit(X[train_idx], y[train_idx])
        oof_probabilities.append(_probability_matrix(fold_model, X[test_idx]))
        oof_y.append(y[test_idx]); oof_returns.append(returns[test_idx]); oof_costs.append(costs[test_idx])
    if not oof_probabilities:
        return None

    raw_oof = np.concatenate(oof_probabilities)
    target_oof = np.concatenate(oof_y)
    returns_oof = np.concatenate(oof_returns)
    costs_oof = np.concatenate(oof_costs)
    calibration_end = max(20, len(target_oof) // 2)
    if len(target_oof) - calibration_end < 20:
        return None

    calibrators: dict[int, object | None] = {}
    for column, label in enumerate((SELL_CLASS, NO_TRADE_CLASS, BUY_CLASS)):
        binary = (target_oof[:calibration_end] == label).astype(float)
        if len(set(binary.tolist())) < 2:
            calibrators[label] = None
        else:
            calibrators[label] = IsotonicRegression(out_of_bounds="clip").fit(
                raw_oof[:calibration_end, column], binary
            )

    tuned_probs = _apply_calibration(raw_oof[calibration_end:], calibrators)
    tuned_returns = returns_oof[calibration_end:]
    tuned_costs = costs_oof[calibration_end:]
    buy = _tune_threshold(tuned_probs[:, 2], tuned_returns, tuned_costs, BUY_CLASS)
    sell = _tune_threshold(tuned_probs[:, 0], tuned_returns, tuned_costs, SELL_CLASS)

    final_model = pipeline()
    final_model.fit(X, y)
    return SegmentModel(
        model=final_model,
        calibrators=calibrators,
        market=market or "ALL",
        regime=regime or "ALL",
        scope=scope,
        sample_size=len(samples),
        buy=buy,
        sell=sell,
    )


def _cached_fit(db: Session, market: str | None, regime: str | None, scope: str) -> SegmentModel | None:
    key = (str(db.get_bind().url), market or "ALL", regime or "ALL")
    session = _calibration_session(market)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] == session:
            return cached[1]
    fitted = _fit_segment(db, market, regime, scope)
    with _cache_lock:
        _cache[key] = (session, fitted)
    return fitted


def _current_vector(db: Session, asset_id: str, feature: DailyAssetFeatureORM) -> list[float]:
    row = db.scalar(
        select(MLTrainingRowORM)
        .where(MLTrainingRowORM.asset_id == asset_id)
        .order_by(MLTrainingRowORM.snapshot_at.desc())
        .limit(1)
    )
    if row is not None and row.snapshot_at.date() == feature.snapshot_at.date():
        try:
            return _vector(json.loads(row.feature_json))
        except (TypeError, json.JSONDecodeError):
            pass
    return _vector({name: getattr(feature, name, 0.0) for name in FEATURE_NAMES})


def _walk_forward_gate(db: Session, market: str, regime: str) -> tuple[bool, str | None]:
    """Blokuje live trade, jeśli nietknięty test nie potwierdza segmentu."""
    from app.db.models import RecommendationAuditRunORM

    row = db.scalar(
        select(RecommendationAuditRunORM)
        .where(RecommendationAuditRunORM.model_version == "walk_forward_v2")
        .order_by(RecommendationAuditRunORM.created_at.desc())
        .limit(1)
    )
    if row is None:
        return True, None
    try:
        report = json.loads(row.result_json)
        market_metric = next((item for item in report.get("by_market", []) if item.get("name") == market), None)
        regime_metric = next((item for item in report.get("by_regime", []) if item.get("name") == regime), None)

        def accepted(metric: dict | None, minimum_trades: int) -> bool:
            if not metric or int(metric.get("trades", 0)) < minimum_trades:
                return False
            profit_factor = metric.get("profit_factor")
            return (
                float(metric.get("avg_net_return_pct", 0.0)) > 0
                and profit_factor is not None
                and float(profit_factor) > 1.0
            )

        failures = []
        if not accepted(market_metric, 50):
            failures.append(f"rynek {market}")
        if not accepted(regime_metric, 30):
            failures.append(f"reżim {regime}")
        if failures:
            return False, "Audyt walk-forward nie potwierdza jeszcze dodatniej przewagi: " + ", ".join(failures) + "."
        return True, None
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, "Najnowszy raport walk-forward jest niepoprawny; transakcja została bezpiecznie zablokowana."


def calibrate_recommendation(
    db: Session,
    asset: AssetORM,
    feature: DailyAssetFeatureORM,
) -> CalibratedDecision:
    import numpy as np

    market = market_segment(asset)
    regime = feature.regime_label
    candidates = (
        (market, regime, "market_regime"),
        (market, None, "market"),
        (None, regime, "regime"),
        (None, None, "global"),
    )
    segment = next(
        (model for m, r, scope in candidates if (model := _cached_fit(db, m, r, scope)) is not None),
        None,
    )
    cost = transaction_cost_pct(market)
    if segment is None:
        return CalibratedDecision(
            action="NO_TRADE", confidence_probability=0.0,
            probability_buy=0.0, probability_sell=0.0, probability_no_trade=1.0,
            market=market, regime=regime, scope="insufficient_data", sample_size=0,
            buy_threshold=1.01, sell_threshold=1.01, transaction_cost_pct=cost,
            expected_gross_edge_pct=0.0, expected_net_edge_pct=0.0, uncertainty_pct=0.0,
            no_trade_reason="Za mało historycznych obserwacji do wiarygodnej kalibracji.",
        )

    raw = _probability_matrix(segment.model, np.asarray([_current_vector(db, asset.id, feature)]))
    calibrated = _apply_calibration(raw, segment.calibrators)[0]
    p_sell, p_no_trade, p_buy = (float(value) for value in calibrated)
    buy_pass = p_buy >= segment.buy.threshold and segment.buy.expected_net_pct > segment.buy.uncertainty_pct
    sell_pass = p_sell >= segment.sell.threshold and segment.sell.expected_net_pct > segment.sell.uncertainty_pct

    if buy_pass and (not sell_pass or p_buy - segment.buy.threshold >= p_sell - segment.sell.threshold):
        action, stats, confidence, reason = "BUY", segment.buy, p_buy, None
    elif sell_pass:
        action, stats, confidence, reason = "SELL", segment.sell, p_sell, None
    else:
        action, confidence = "NO_TRADE", p_no_trade
        best = segment.buy if p_buy - segment.buy.threshold >= p_sell - segment.sell.threshold else segment.sell
        stats = best
        if best.threshold > 1:
            reason = "Historia nie potwierdza dodatniej przewagi po kosztach dla tego segmentu."
        elif best.expected_net_pct <= best.uncertainty_pct:
            reason = "Oczekiwana przewaga netto nie pokrywa niepewności historycznej."
        else:
            reason = "Prawdopodobieństwo sygnału nie przekracza skalibrowanego progu wejścia."

    if action in {"BUY", "SELL"}:
        audit_allowed, audit_reason = _walk_forward_gate(db, market, regime)
        if not audit_allowed:
            action, confidence, reason = "NO_TRADE", p_no_trade, audit_reason

    return CalibratedDecision(
        action=action,
        confidence_probability=confidence,
        probability_buy=p_buy,
        probability_sell=p_sell,
        probability_no_trade=p_no_trade,
        market=market,
        regime=regime,
        scope=segment.scope,
        sample_size=segment.sample_size,
        buy_threshold=segment.buy.threshold,
        sell_threshold=segment.sell.threshold,
        transaction_cost_pct=cost,
        expected_gross_edge_pct=stats.expected_gross_pct,
        expected_net_edge_pct=stats.expected_net_pct,
        uncertainty_pct=stats.uncertainty_pct,
        no_trade_reason=reason,
    )


def invalidate_calibration_cache(*, force: bool = False) -> None:
    """Drop stale sessions, preserving today's frozen live calibration.

    Scheduler dataset refreshes call this function every hour. Clearing the
    entire cache there used to refit thresholds intraday. ``force`` remains
    available for tests and explicit administrative maintenance.
    """
    with _cache_lock:
        if force:
            _cache.clear()
            return
        stale = []
        for key, (session, _) in _cache.items():
            market = None if key[1] == "ALL" else key[1]
            if session != _calibration_session(market):
                stale.append(key)
        for key in stale:
            _cache.pop(key, None)
