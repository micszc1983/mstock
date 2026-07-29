from __future__ import annotations

import json
import uuid
from pathlib import Path
from statistics import mean
from typing import Dict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.assets import list_assets
from app.repositories.decision_support import get_latest_decision_snapshot
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.ml import (
    count_training_rows,
    delete_training_row_for_timestamp,
    get_active_model_run,
    get_active_market_model_runs,
    get_all_active_model_runs,
    get_latest_prediction,
    get_setting,
    insert_backtest_result,
    insert_model_run,
    insert_prediction,
    delete_predictions_older_than,
    insert_training_row,
    list_backtest_results,
    list_model_runs,
    list_training_rows,
    list_training_rows_for_target,
    upsert_setting,
)
from app.repositories.outcomes import list_outcomes_for_asset, list_outcomes_for_thesis
from app.repositories.features import list_feature_history
from app.repositories.theses import list_thesis_history
from app.utils.datetime import ensure_utc
from app.schemas.ml import (
    ML_TARGETS,
    ML_TARGET_LABELS,
    MLActiveModel,
    MLDatasetBuildResponse,
    MLDatasetStatsResponse,
    MLStatusResponse,
    MLExplanationResponse,
    MLFeatureImportance,
    MLPredictionContribution,
)


def get_ml_mode(db: Session) -> bool:
    from app.services.ml_activation import automatic_activation_summary
    return bool(automatic_activation_summary(db)["enabled"])


def set_ml_mode(db: Session, enabled: bool) -> bool:
    from app.services.ml_activation import set_emergency_disabled
    set_emergency_disabled(db, not enabled)
    return get_ml_mode(db)


def _models_dir() -> Path:
    path = Path(settings.ml_models_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _poc_distance(closes: list[float], volumes: list[float], window: int = 30) -> float:
    """Odległość bieżącej ceny od POC (Point of Control) w %, obliczona z ostatnich `window` świec dziennych.
    Dodatnia = cena nad POC, ujemna = pod POC."""
    if len(closes) < window or not volumes:
        return 0.0
    w_c = closes[-window:]
    w_v = volumes[-window:]
    p_lo, p_hi = min(w_c), max(w_c)
    if p_hi <= p_lo:
        return 0.0
    num_bins = 20
    bin_size = (p_hi - p_lo) / num_bins
    bins = [0.0] * num_bins
    for c, v in zip(w_c, w_v):
        b = min(int((c - p_lo) / bin_size), num_bins - 1)
        bins[b] += v
    poc_idx = max(range(num_bins), key=lambda i: bins[i])
    poc = p_lo + (poc_idx + 0.5) * bin_size
    cur = w_c[-1]
    return round((cur - poc) / max(poc, 1e-9) * 100, 3)


def _rs_vs_sector(asset_closes: list[float], sector_closes: list[float], window: int = 20) -> float:
    """Zwrot aktywa minus zwrot sektora ETF za ostatnie `window` sesji (relative strength)."""
    if len(asset_closes) <= window or len(sector_closes) <= window:
        return 0.0
    asset_ret = (asset_closes[-1] - asset_closes[-window - 1]) / asset_closes[-window - 1] * 100
    sector_ret = (sector_closes[-1] - sector_closes[-window - 1]) / sector_closes[-window - 1] * 100
    return round(asset_ret - sector_ret, 3)


_FEATURE_NAMES = [
    # Cechy z feature snapshot (trend, sentyment)
    "trend_score",
    "sentiment_score",
    "divergence_score",
    "fragility_score",
    "narrative_shift_score",
    "volatility_10d",
    "momentum_20d",
    "news_count_7d",
    "price_change_1d_pct",
    "price_change_5d_pct",
    "price_change_20d_pct",
    # Wskaźniki techniczne obliczane z OHLCV
    "rsi_14",
    "macd_histogram",
    "bb_pct",
    "volume_ratio_20d",
    "price_vs_52w_high",
    "above_sma200",
    # Kontekst rynkowy (SPY)
    "spy_return_5d",
    "alpha_vs_spy_5d",
    # Dane makroekonomiczne (VIX, Treasury, DXY)
    "vix_level",
    "vix_change_5d",
    "treasury_10y",
    "dxy_return_5d",
    # Siła sektora (ETF: SOXX dla półprzewodników, QQQ dla tech/AI)
    "sector_return_5d",
    "sector_vs_spy_5d",
    # ── Nowe cechy XGBoost ──────────────────────────────────────────────────────
    "day_of_week",          # 0=Pon … 4=Pią (sezonowość tygodniowa)
    "days_to_earnings",     # dni do najbliższego raportu (max 90); wyniki zbliżają → volatility
    "iv_rank",              # percentyl IV w 252-dniowym oknie (0-100); wysoki = drogie opcje = duży ruch
    "rs_vs_sector_20d",     # zwrot aktywa - zwrot sektora ETF za 20 sesji (siła względna)
    "poc_distance_pct",     # % odległość ceny od POC 30-dniowego volume profile (>0=nad POC)
    # Dane point-in-time: jawne braki + zdarzenia fundamentalne/newsowe.
    "has_iv", "has_upcoming_earnings",
    "has_earnings", "days_since_earnings", "eps_surprise_pct",
    "revenue_surprise_pct", "has_pead_1d", "pead_return_1d_pct",
    "has_pead_5d", "pead_return_5d_pct",
    "has_insider_90d", "insider_net_value_log_90d", "insider_buy_ratio_90d",
    "insider_cluster_buyers_90d", "days_since_insider_filing",
    "has_short_interest", "short_percent_float", "short_ratio", "short_percent_change",
    "news_event_positive_7d", "news_event_negative_7d",
    "news_event_earnings_guidance_7d", "news_event_corporate_action_7d",
    "news_event_financing_7d", "news_event_legal_regulatory_7d",
    "news_event_contract_product_7d", "news_event_management_cyber_7d",
    "news_attention_zscore_7d", "news_source_diversity_7d", "news_high_impact_7d",
    "news_nlp_coverage_7d", "news_relevance_mean_7d", "news_sentiment_confidence_mean_7d",
]

# Mapowanie asset → sektor ETF w naszej bazie
_SECTOR_ETF_MAP: Dict[str, str] = {
    # Półprzewodniki → SOXX
    "nvda": "soxx", "amd": "soxx", "avgo": "soxx",
    # Szeroki tech/AI → QQQ
    "aapl": "qqq", "msft": "qqq", "googl": "qqq", "amzn": "qqq",
    "meta": "qqq", "tsla": "qqq", "orcl": "qqq", "pltr": "qqq",
    "botz": "qqq", "aiq":  "qqq",
    # ETF-y same w sobie — porównaj ze sobą
    "qqq":  "qqq", "soxx": "soxx",
    # GPW i metale — brak sektorowego ETF w naszej bazie, fallback = SPY (sector=0)
}


def _feature_vector(db: Session, asset_id: str) -> tuple[dict | None, object | None]:
    from app.repositories.prices import list_prices
    from app.mappers import price_to_schema
    from app.services.technical_indicators import compute_all, fetch_spy_returns, fetch_macro_data

    feature = get_latest_feature_snapshot(db, asset_id)
    if feature is None:
        return None, None

    # Załaduj wyłącznie ceny znane w chwili snapshotu. To ma znaczenie również
    # dla ręcznego scoringu starszego snapshotu po późniejszym dosypaniu cen.
    snapshot_dt = ensure_utc(feature.snapshot_at)
    all_prices = sorted(
        [
            price_to_schema(p) for p in list_prices(db, asset_id)
            if ensure_utc(p.timestamp) <= snapshot_dt
        ],
        key=lambda p: ensure_utc(p.timestamp)
    )[-260:]

    closes  = [p.close  for p in all_prices]
    volumes = [p.volume for p in all_prices]

    snap_date = snapshot_dt.date()
    spy_returns = fetch_spy_returns(settings.twelvedata_api_key) if settings.twelvedata_api_key else {}
    macro_data  = fetch_macro_data()

    # Ceny sektora ETF
    sector_closes: list = []
    sector_etf = _SECTOR_ETF_MAP.get(asset_id)
    if sector_etf:
        sector_prices = sorted(
            [
                price_to_schema(p) for p in list_prices(db, sector_etf)
                if ensure_utc(p.timestamp) <= snapshot_dt
            ],
            key=lambda p: ensure_utc(p.timestamp)
        )[-260:]
        sector_closes = [p.close for p in sector_prices]

    trailing_return_5d = (
        (closes[-1] - closes[-6]) / closes[-6] * 100
        if len(closes) >= 6 and closes[-6] else None
    )
    tech = compute_all(closes, volumes, spy_returns, snap_date, asset_return_5d=trailing_return_5d,
                       macro_data=macro_data, sector_closes=sector_closes)

    # ── Nowe cechy: kalendarz point-in-time, IV, RS, POC ───────────────────────
    import datetime as _dt
    snap_dt = snap_date if isinstance(snap_date, _dt.date) else ensure_utc(feature.snapshot_at).date()
    day_of_week = float(snap_dt.weekday())

    iv_rank_val = float(feature.iv_rank) if feature.iv_rank is not None else 0.0

    volumes = [p.volume for p in all_prices]
    rs_vs_sector_20d = _rs_vs_sector(closes, sector_closes, window=20)
    poc_distance = _poc_distance(closes, volumes, window=30)

    vec = {
        "trend_score":           feature.trend_score,
        "sentiment_score":       feature.sentiment_score,
        "divergence_score":      feature.divergence_score,
        "fragility_score":       feature.fragility_score,
        "narrative_shift_score": feature.narrative_shift_score,
        "volatility_10d":        feature.volatility_10d,
        "momentum_20d":          feature.momentum_20d,
        "news_count_7d":         float(feature.news_count_7d),
        "price_change_1d_pct":   feature.price_change_1d_pct,
        "price_change_5d_pct":   feature.price_change_5d_pct,
        "price_change_20d_pct":  feature.price_change_20d_pct,
        **tech,
        "day_of_week":           day_of_week,
        "days_to_earnings":      90.0,
        "iv_rank":               iv_rank_val,
        "rs_vs_sector_20d":      rs_vs_sector_20d,
        "poc_distance_pct":      poc_distance,
    }
    from app.services.point_in_time_features import PointInTimeFeatureStore
    point_in_time = PointInTimeFeatureStore(db, asset_id)
    vec.update(point_in_time.build(
        feature.snapshot_at,
        has_iv=getattr(feature, "implied_volatility", None) is not None,
        price_dates=[ensure_utc(p.timestamp).date() for p in all_prices],
        closes=closes,
    ))
    return vec, feature


def build_training_dataset(db: Session) -> MLDatasetBuildResponse:
    """
    Buduje dataset ML z historii cen + feature snapshotów.
    Cechy: fundamenty z feature snapshot + wskaźniki techniczne (RSI, MACD, BB, volume)
           + kontekst rynkowy (SPY return, alpha).

    Etykiety (target_up_*) są wyliczane z cen historycznych:
      target_up_1d/5d/20d = 1 jeśli cena za N dni handlowych > cena dziś
    """
    from app.repositories.prices import list_prices
    from app.mappers import price_to_schema
    from app.services.technical_indicators import compute_all, fetch_spy_returns, fetch_macro_data

    # Pobierz dane zewnętrzne raz dla całego datasetu
    spy_returns = fetch_spy_returns(settings.twelvedata_api_key) if settings.twelvedata_api_key else {}
    if spy_returns:
        print(f"[ml] SPY returns loaded: {len(spy_returns)} dni")
    else:
        print("[ml] SPY returns niedostępne — alpha_vs_spy_5d = 0")

    macro_data = fetch_macro_data()
    if macro_data:
        print(f"[ml] Dane makro załadowane: {len(macro_data)} dni (VIX, Treasury, DXY)")
    else:
        print("[ml] Dane makro niedostępne — vix/treasury/dxy = 0")

    # Preload cen ETF sektora (do sił sektorowych) — raz dla wszystkich aktywów
    sector_price_map: Dict[str, Dict] = {}  # etf_id → {date: close}
    for etf_id in set(_SECTOR_ETF_MAP.values()):
        etf_prices = sorted(
            [price_to_schema(p) for p in list_prices(db, etf_id)],
            key=lambda p: ensure_utc(p.timestamp)
        )
        if etf_prices:
            sector_price_map[etf_id] = {
                ensure_utc(p.timestamp).date(): p.close for p in etf_prices
            }
    if sector_price_map:
        print(f"[ml] Ceny sektora ETF załadowane: {list(sector_price_map.keys())}")

    # Training rows are fully derived data. Rebuilding in one transaction avoids
    # leaving stale rows with an older feature schema (which could silently make
    # the trainer infer the old column list from its first row).
    from sqlalchemy import delete as _delete
    from app.db.models import MLTrainingRowORM
    db.execute(_delete(MLTrainingRowORM))

    built = 0
    for asset in list_assets(db):
        from app.services.recommendation_calibration import market_segment, transaction_cost_pct
        asset_transaction_cost = transaction_cost_pct(market_segment(asset))
        # Wczytaj wszystkie ceny posortowane chronologicznie
        all_prices = sorted(
            [price_to_schema(p) for p in list_prices(db, asset.id)],
            key=lambda p: ensure_utc(p.timestamp)
        )
        if len(all_prices) < 5:
            continue

        from app.services.point_in_time_features import PointInTimeFeatureStore
        point_in_time = PointInTimeFeatureStore(db, asset.id)

        # Słowniki: date → wartość
        price_by_date: dict = {}
        volume_by_date: dict = {}
        for p in all_prices:
            d = ensure_utc(p.timestamp).date()
            price_by_date[d] = p.close
            volume_by_date[d] = p.volume

        sorted_dates = sorted(price_by_date.keys())
        date_index = {d: i for i, d in enumerate(sorted_dates)}

        # Posortowane listy dla okien wskaźników (szybszy dostęp)
        all_closes  = [price_by_date[d] for d in sorted_dates]
        all_volumes = [volume_by_date.get(d, 0.0) for d in sorted_dates]
        high_by_date = {
            ensure_utc(point.timestamp).date(): point.high for point in all_prices
        }
        low_by_date = {
            ensure_utc(point.timestamp).date(): point.low for point in all_prices
        }
        all_highs = [high_by_date.get(day, price_by_date[day]) for day in sorted_dates]
        all_lows = [low_by_date.get(day, price_by_date[day]) for day in sorted_dates]

        def price_after_n_days(base_date, n: int):
            idx = date_index.get(base_date)
            if idx is None:
                return None
            target_idx = idx + n
            if target_idx >= len(sorted_dates):
                return None
            return price_by_date[sorted_dates[target_idx]]

        # Thesis outcomes (fallback)
        outcome_map: dict = {}
        for thesis in list_thesis_history(db, asset.id, limit=500):
            snap_date = ensure_utc(thesis.source_snapshot_at).date()
            for outcome in list_outcomes_for_thesis(db, thesis.id):
                key = (snap_date, outcome.horizon)
                if key not in outcome_map:
                    outcome_map[key] = outcome

        # --- Iteruj po historii feature snapshotów ---
        for feat in list_feature_history(db, asset.id, limit=1000):
            snap_date = ensure_utc(feat.snapshot_at).date()
            idx = date_index.get(snap_date)
            if idx is None:
                continue

            # Cechy z feature snapshot (trend, sentyment, momentum)
            base_vec = {
                "trend_score":           feat.trend_score,
                "sentiment_score":       feat.sentiment_score,
                "divergence_score":      feat.divergence_score,
                "fragility_score":       feat.fragility_score,
                "narrative_shift_score": feat.narrative_shift_score,
                "volatility_10d":        feat.volatility_10d,
                "momentum_20d":          feat.momentum_20d,
                "news_count_7d":         float(feat.news_count_7d),
                "price_change_1d_pct":   feat.price_change_1d_pct,
                "price_change_5d_pct":   feat.price_change_5d_pct,
                "price_change_20d_pct":  feat.price_change_20d_pct,
            }

            # Oblicz targety (potrzebne też dla alpha vs SPY)
            targets: dict = {
                "target_up_1d": None, "target_up_5d": None, "target_up_20d": None,
                "target_return_1d": None, "target_return_5d": None, "target_return_20d": None,
                "target_thesis_success": None,
                "target_triple_barrier": None, "target_meta_label": None,
                "triple_barrier_return_pct": None, "triple_barrier_hit": None,
                "meta_side": None, "meta_strategy_return_pct": None,
                "market_segment": market_segment(asset),
                "market_regime": feat.regime_label,
                "meta_primary_probability": None, "meta_primary_margin": None,
                "meta_model_disagreement": None, "meta_label_source": "heuristic_primary",
            }
            base_price = price_by_date.get(snap_date)
            ret_5d = None
            if base_price and base_price > 0:
                for n_days, horizon in [(1, "1d"), (5, "5d"), (20, "20d")]:
                    future_price = price_after_n_days(snap_date, n_days)
                    if future_price is not None:
                        ret = (future_price - base_price) / base_price * 100
                        targets[f"target_up_{horizon}"] = int(ret > 0)
                        targets[f"target_return_{horizon}"] = round(ret, 4)
                        if horizon == "5d":
                            ret_5d = ret
                if targets["target_up_5d"] is not None:
                    targets["target_thesis_success"] = targets["target_up_5d"]
            else:
                for horizon in ("1d", "5d", "20d"):
                    outcome = outcome_map.get((snap_date, horizon))
                    if outcome is not None:
                        targets[f"target_up_{horizon}"] = int(outcome.realized_return_pct > 0)
                        targets[f"target_return_{horizon}"] = outcome.realized_return_pct
                        if horizon == "5d":
                            ret_5d = outcome.realized_return_pct
                            targets["target_thesis_success"] = int(outcome.was_directionally_correct)

            # Ceny sektora ETF do snap_date (okno 260 dni)
            sector_closes: list = []
            sector_etf = _SECTOR_ETF_MAP.get(asset.id)
            if sector_etf and sector_etf in sector_price_map:
                etf_by_date = sector_price_map[sector_etf]
                etf_dates   = sorted(d for d in etf_by_date if d <= snap_date)[-260:]
                sector_closes = [etf_by_date[d] for d in etf_dates]

            # Wskaźniki techniczne obliczane wyłącznie z okna do snap_date.
            # UWAGA: alpha_vs_spy musi używać historycznego zwrotu T-5..T.
            # Przekazanie targetu T..T+5 byłoby bezpośrednim przeciekiem etykiety.
            window_closes  = all_closes[:idx + 1]
            window_volumes = all_volumes[:idx + 1]
            trailing_return_5d = (
                (window_closes[-1] - window_closes[-6]) / window_closes[-6] * 100
                if len(window_closes) >= 6 and window_closes[-6] else None
            )
            tech = compute_all(window_closes, window_volumes, spy_returns, snap_date, trailing_return_5d,
                               macro_data=macro_data, sector_closes=sector_closes)

            # ── Nowe cechy ────────────────────────────────────────────────────────
            day_of_week = float(snap_date.weekday())
            iv_rank_val = float(feat.iv_rank) if getattr(feat, "iv_rank", None) is not None else 0.0
            sector_closes_window = []
            sector_etf2 = _SECTOR_ETF_MAP.get(asset.id)
            if sector_etf2 and sector_etf2 in sector_price_map:
                etf_by_date2 = sector_price_map[sector_etf2]
                s_dates2 = sorted(d for d in etf_by_date2 if d <= snap_date)[-260:]
                sector_closes_window = [etf_by_date2[d] for d in s_dates2]
            rs_vs_sector_20d = _rs_vs_sector(window_closes, sector_closes_window, window=20)
            poc_distance = _poc_distance(window_closes, window_volumes, window=30)

            vec = {
                **base_vec,
                **tech,
                "day_of_week":      day_of_week,
                "days_to_earnings": 90.0,
                "iv_rank":          iv_rank_val,
                "rs_vs_sector_20d": rs_vs_sector_20d,
                "poc_distance_pct": poc_distance,
            }
            vec.update(point_in_time.build(
                feat.snapshot_at,
                has_iv=getattr(feat, "implied_volatility", None) is not None,
                price_dates=sorted_dates,
                closes=all_closes,
            ))

            from app.services.triple_barrier import build_triple_barrier_outcome, primary_side
            barrier = build_triple_barrier_outcome(
                all_closes, all_highs, all_lows, idx,
                side=primary_side(vec), transaction_cost_pct=asset_transaction_cost,
                horizon_sessions=settings.triple_barrier_horizon_sessions,
                take_profit_vol_multiplier=settings.triple_barrier_take_profit_vol_multiplier,
                stop_loss_vol_multiplier=settings.triple_barrier_stop_loss_vol_multiplier,
            )
            if barrier is not None:
                targets.update({
                    "target_triple_barrier": barrier.direction_label,
                    "target_meta_label": barrier.meta_label,
                    "triple_barrier_return_pct": barrier.raw_return_pct,
                    "triple_barrier_hit": barrier.hit,
                    "meta_side": barrier.side,
                    "meta_strategy_return_pct": barrier.strategy_net_return_pct,
                })

            delete_training_row_for_timestamp(db, asset.id, feat.snapshot_at)
            insert_training_row(
                db,
                asset_id=asset.id,
                snapshot_at=feat.snapshot_at,
                feature_json=json.dumps(vec, ensure_ascii=False),
                **targets,
            )
            built += 1

    db.commit()
    return MLDatasetBuildResponse(built_rows=built, total_rows=count_training_rows(db))


def dataset_stats(db: Session) -> MLDatasetStatsResponse:
    from sqlalchemy import func, select
    from app.db.models import MLTrainingRowORM

    total = count_training_rows(db)
    assets = dict(db.execute(
        select(MLTrainingRowORM.asset_id, func.count())
        .group_by(MLTrainingRowORM.asset_id)
    ).all())

    def labeled(column) -> int:
        return int(db.scalar(
            select(func.count()).select_from(MLTrainingRowORM).where(column.is_not(None))
        ) or 0)

    return MLDatasetStatsResponse(
        total_rows=total,
        assets=assets,
        labeled_rows_1d=labeled(MLTrainingRowORM.target_up_1d),
        labeled_rows_5d=labeled(MLTrainingRowORM.target_up_5d),
        labeled_rows_20d=labeled(MLTrainingRowORM.target_up_20d),
        thesis_success_rows=labeled(MLTrainingRowORM.target_thesis_success),
        triple_barrier_rows=labeled(MLTrainingRowORM.target_triple_barrier),
        meta_label_rows=labeled(MLTrainingRowORM.target_meta_label),
        oof_meta_label_rows=int(db.scalar(
            select(func.count()).select_from(MLTrainingRowORM).where(
                MLTrainingRowORM.meta_label_source == "purged_oof_primary"
            )
        ) or 0),
    )


def status(db: Session) -> MLStatusResponse:
    from sqlalchemy import select
    from app.db.models import MLModelRunORM

    from app.services.ml_activation import automatic_activation_summary
    activation = automatic_activation_summary(db)
    activation_by_run = {
        decision.model_run_id: decision for decision in activation["decisions"]
    }
    enabled = bool(activation["enabled"])
    total = count_training_rows(db)

    # Zbierz stan dla każdego targetu
    target_states: list[MLActiveModel] = []
    first_active = None
    for target in ML_TARGETS:
        # Status globalny ma pokazać również championów per-asset; repozytoryjne
        # get_active_model_run(..., asset_id=None) celowo zwraca wyłącznie model globalny.
        active_runs = list(db.scalars(
            select(MLModelRunORM)
            .where(
                MLModelRunORM.target_name == target,
                MLModelRunORM.is_active.is_(True),
            )
            .order_by(MLModelRunORM.trained_at.desc())
        ).all())
        active = active_runs[0] if active_runs else None
        if active and first_active is None:
            first_active = active
        labeled = _count_labeled(db, target)
        decisions = [activation_by_run[run.id] for run in active_runs if run.id in activation_by_run]
        eligible_count = sum(decision.eligible for decision in decisions)
        degraded_count = sum(decision.state == "degraded" for decision in decisions)
        shadow_count = len(decisions) - eligible_count - degraded_count
        target_state = (
            "eligible" if eligible_count and eligible_count == len(decisions)
            else "partial" if eligible_count
            else "degraded" if degraded_count
            else "shadow" if active_runs
            else "untrained"
        )
        target_states.append(MLActiveModel(
            target_name=target,
            target_label=ML_TARGET_LABELS.get(target, target),
            model_name=active.model_name if active else None,
            is_trained=active is not None,
            dataset_rows=labeled,
            active_models=len(active_runs), eligible_models=eligible_count,
            shadow_models=shadow_count, degraded_models=degraded_count,
            activation_state=target_state,
        ))

    return MLStatusResponse(
        ml_mode=activation["mode"],
        ml_enabled=enabled,
        active_model_name=first_active.model_name if first_active else None,
        active_target_name=first_active.target_name if first_active else None,
        dataset_rows=total,
        min_training_rows=settings.ml_min_training_rows,
        ready_for_training=total >= settings.ml_min_training_rows,
        activation_mode="automatic",
        emergency_disabled=activation["emergency_disabled"],
        active_models=activation["active_models"],
        eligible_models=activation["eligible_models"],
        shadow_models=activation["shadow_models"],
        degraded_models=activation["degraded_models"],
        targets=target_states,
    )


def _count_labeled(db: Session, target_name: str) -> int:
    """Liczy wiersze z wypełnionym targetem — bez ładowania wszystkich do pamięci."""
    from sqlalchemy import func as _func
    from app.db.models import MLTrainingRowORM
    from sqlalchemy import select as _sel
    col = getattr(MLTrainingRowORM, target_name, None)
    if col is None:
        return 0
    return db.scalar(_sel(_func.count()).select_from(MLTrainingRowORM).where(col.isnot(None))) or 0


def train_all_targets(db: Session) -> list:
    """Trenuje champion–challenger dla targetów bezpośrednio używanych w decyzji."""
    results = []
    assets = list_assets(db)
    targets = (
        "target_up_5d",
        "target_up_20d",
        "target_triple_barrier",
        "target_meta_label",
    )
    for asset in assets:
        for target in targets:
            rows = list_training_rows_for_target(db, target, asset_id=asset.id)
            if len(rows) < settings.ml_min_training_rows:
                results.append({"asset": asset.id, "target": target, "skipped": True, "reason": "za mało danych"})
                continue
            try:
                outcome = train_champion_challengers(db, target_name=target, asset_id=asset.id)
                results.append({"asset": asset.id, "target": target, "skipped": False, **outcome})
            except Exception as exc:
                results.append({"asset": asset.id, "target": target, "skipped": True, "reason": str(exc)})
    if settings.ml_market_models_enabled:
        for market in ("GPW", "USA"):
            for target in targets:
                try:
                    outcome = train_champion_challengers(
                        db, target_name=target, asset_id=None, market=market,
                    )
                    results.append({"asset": None, "market": market, "target": target, "skipped": False, **outcome})
                except Exception as exc:
                    results.append({"asset": None, "market": market, "target": target, "skipped": True, "reason": str(exc)})
        # Modele rynku są fallbackiem dla aktywów bez bezpiecznego championa.
        # Po ich treningu odświeżamy predykcje, aby fallback nie czekał do schedulera.
        for asset in assets:
            for target in targets:
                try:
                    score_asset(db, asset.id, target)
                except Exception as exc:
                    results.append({
                        "asset": asset.id, "target": target, "scoring_skipped": True,
                        "reason": f"market fallback scoring: {exc}",
                    })
    return results


def _xy(rows, target_name: str, feature_names: list[str] | None = None):
    from app.services.meta_labeling import enrich_meta_features

    X, y = [], []
    names = feature_names
    for row in rows:
        features = json.loads(row.feature_json)
        if target_name == "target_meta_label":
            features = enrich_meta_features(features, row=row)
        if names is None:
            names = list(features.keys())
        X.append([float(features.get(k, 0.0) or 0.0) for k in names])
        y.append(int(getattr(row, target_name)))
    return X, y, names or []


def train_model(
    db: Session,
    target_name: str = "target_up_5d",
    model_name: str = "logistic_regression",
    asset_id: str | None = None,
    market: str | None = None,
    use_optuna: bool = False,
    optuna_trials: int = 30,
    activate: bool = False,
):
    from app.services.ml_models.registry import (
        train_single_model as _train_single,
        cv_score_model as _cv_score,
        cpcv_score_model as _cpcv_score,
        optimize_model as _optimize,
    )

    rows = list_training_rows_for_target(
        db, target_name, asset_id=asset_id, market_segment=market,
    )
    if target_name == "target_meta_label":
        rows = [
            row for row in rows
            if row.meta_label_source == "purged_oof_primary"
            and row.meta_primary_probability is not None
        ]
    if len(rows) < settings.ml_min_training_rows:
        raise ValueError(f"Not enough rows to train. Need at least {settings.ml_min_training_rows}, got {len(rows)}")

    # Enriched groups are challenger features. They enter training only after a
    # saved purged-CV ablation has improved F1, calibration and net return.
    first_features = json.loads(rows[0].feature_json)
    if target_name == "target_meta_label":
        from app.services.meta_labeling import enrich_meta_features
        first_features = enrich_meta_features(first_features, row=rows[0])
    from app.services.feature_ablation import approved_feature_names_for_training
    approved_names = approved_feature_names_for_training(
        db, list(first_features), target_name=target_name,
        asset_id=asset_id, market=market,
    )
    X_all, y_all, feature_names = _xy(rows, target_name, approved_names)

    horizon_gap = 20 if target_name == "target_up_20d" else (
        settings.triple_barrier_horizon_sessions
        if target_name in {"target_triple_barrier", "target_meta_label"}
        else 5
    )
    groups = [ensure_utc(row.snapshot_at).date() for row in rows]

    # ── 1. Optuna hyperparameter search (opcjonalne) ─────────────────────────
    best_params: dict | None = None
    optuna_result: dict = {}
    if use_optuna:
        print(f"[ml] Optuna search: {model_name}/{target_name} ({optuna_trials} trials)…")
        best_params = _optimize(
            model_name, X_all, y_all, n_trials=optuna_trials,
            groups=groups, purge_sessions=horizon_gap,
        )
        if best_params:
            print(f"[ml] Optuna best params: {best_params}")
            optuna_result = {"optuna_best_params": best_params, "optuna_trials": optuna_trials}

    # ── 2. Train / późniejsza kalibracja / nietknięty holdout ───────────────
    unique_groups = list(dict.fromkeys(groups))
    fraction = min(0.25, max(0.10, settings.ml_calibration_fraction))
    split_group = max(int(len(unique_groups) * (1.0 - fraction)), 1)
    calibration_end_group = max(1, split_group - horizon_gap)
    calibration_sessions = max(20, int(len(unique_groups) * fraction))
    calibration_start_group = max(1, calibration_end_group - calibration_sessions)
    train_end_group = max(1, calibration_start_group - horizon_gap)
    train_group_set = set(unique_groups[:train_end_group])
    calibration_group_set = set(unique_groups[calibration_start_group:calibration_end_group])
    test_group_set = set(unique_groups[split_group:])
    train_rows = [row for row, group in zip(rows, groups) if group in train_group_set]
    calibration_rows = [row for row, group in zip(rows, groups) if group in calibration_group_set]
    test_rows = [row for row, group in zip(rows, groups) if group in test_group_set]
    if not test_rows or len(calibration_rows) < 20:
        raise ValueError("Not enough rows for purged calibration and out-of-sample sets")
    X_train, y_train, _ = _xy(train_rows, target_name, feature_names)
    X_cal, y_cal, _ = _xy(calibration_rows, target_name, feature_names)
    X_test,  y_test,  _ = _xy(test_rows, target_name, feature_names)

    asset_suffix = f"_{asset_id}" if asset_id else f"_{market}" if market else ""
    model_path = _models_dir() / f"{model_name}_{target_name}{asset_suffix}_{uuid.uuid4().hex[:10]}.joblib"

    model_metrics = _train_single(
        model_name, X_train, y_train, X_test, y_test, feature_names,
        str(model_path), best_params=best_params, X_cal=X_cal, y_cal=y_cal,
    )

    # ── 3. Purged temporal CV na całym datasecie ─────────────────────────────
    cv_metrics: dict = {}
    try:
        cv_result = _cv_score(
            model_name, X_all, y_all, feature_names, n_splits=5,
            best_params=best_params, groups=groups, purge_sessions=horizon_gap,
        )
        if cv_result:
            cv_metrics = cv_result
            print(f"[ml] CV {model_name}: acc={cv_result['cv_accuracy_mean']:.3f}±{cv_result['cv_accuracy_std']:.3f}  "
                  f"f1={cv_result['cv_f1_mean']:.3f}±{cv_result['cv_f1_std']:.3f}")
    except Exception as exc:
        print(f"[ml] CV skipped: {exc}")

    cpcv_metrics: dict = {}
    if settings.ml_cpcv_enabled:
        try:
            cpcv_metrics = _cpcv_score(
                model_name, X_all, y_all, groups,
                purge_sessions=horizon_gap, best_params=best_params,
            )
        except Exception as exc:
            print(f"[ml] CPCV skipped: {exc}")

    trading_metrics = _holdout_trading_metrics(
        db, model_path, model_name, feature_names, test_rows, X_test,
        target_name, asset_id, market,
    )
    metrics = {
        **model_metrics,
        **cv_metrics,
        **cpcv_metrics,
        **trading_metrics,
        **optuna_result,
        "train_rows": len(train_rows),
        "calibration_rows": len(calibration_rows),
        "test_rows":  len(test_rows),
        "feature_names": feature_names,
        "asset_id": asset_id,
        "market_segment": market,
        "split_index": split_group,
        "embargo_rows": horizon_gap,
        "holdout_method": "purged_group_time_series",
        "train_end": train_rows[-1].snapshot_at.isoformat(),
        "calibration_start": calibration_rows[0].snapshot_at.isoformat(),
        "calibration_end": calibration_rows[-1].snapshot_at.isoformat(),
        "test_start": test_rows[0].snapshot_at.isoformat(),
        "feature_reference": _feature_reference(X_train, feature_names),
    }

    row = insert_model_run(
        db, model_name=model_name, target_name=target_name,
        dataset_rows=len(rows), metrics_json=json.dumps(metrics, ensure_ascii=False),
        model_path=str(model_path), is_active=activate, asset_id=asset_id,
        deployment_role="champion" if activate else "candidate",
        promotion_reason="Jawna promocja podczas treningu" if activate else None,
        market_segment=market,
    )
    db.commit()
    db.refresh(row)
    return row


def _holdout_trading_metrics(
    db: Session,
    model_path,
    model_name: str,
    feature_names: list[str],
    test_rows: list,
    X_test: list,
    target_name: str,
    asset_id: str | None,
    market: str | None,
) -> dict:
    import joblib
    import numpy as np
    from app.repositories.assets import get_asset
    from app.services.recommendation_calibration import market_segment, transaction_cost_pct

    model = joblib.load(model_path)["model"]
    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]
    asset = get_asset(db, asset_id) if asset_id else None
    resolved_market = market_segment(asset) if asset is not None else market or "OTHER"
    cost = transaction_cost_pct(resolved_market)
    returns: list[float] = []
    selected: list[float] = []
    observations = []
    for prediction, probability, row in zip(predictions, probabilities, test_rows):
        if target_name == "target_meta_label":
            value = float(row.meta_strategy_return_pct or 0.0) if int(prediction) == 1 else 0.0
            is_selected = int(prediction) == 1
        else:
            if target_name == "target_up_20d":
                raw = float(row.target_return_20d or 0.0)
            elif target_name == "target_triple_barrier":
                raw = float(row.triple_barrier_return_pct or 0.0)
            else:
                raw = float(row.target_return_5d or 0.0)
            value = (raw if int(prediction) == 1 else -raw) - cost
            is_selected = True
        returns.append(value)
        if is_selected:
            selected.append(value)
        if target_name == "target_meta_label":
            observations.append({
                "probability": round(float(probability), 6),
                "net_return_pct": round(float(row.meta_strategy_return_pct or 0.0), 6),
                "label": int(row.target_meta_label or 0),
                "market": row.market_segment or resolved_market,
                "regime": row.market_regime or "unknown",
            })
    values = np.asarray(returns, dtype=float)
    trades = np.asarray(selected, dtype=float)
    wins = trades[trades > 0]
    losses = trades[trades < 0]
    equity = np.cumprod(1.0 + values / 100.0) if len(values) else np.asarray([1.0])
    peaks = np.maximum.accumulate(equity)
    drawdown = (equity / peaks - 1.0) * 100.0
    from app.services.ml_validation import deflated_sharpe_ratio
    return {
        "holdout_trades": len(selected),
        "holdout_coverage_pct": round(len(selected) / len(test_rows) * 100.0, 4) if test_rows else 0.0,
        "holdout_win_rate_pct": round(float((trades > 0).mean() * 100.0), 4) if len(trades) else 0.0,
        "holdout_avg_net_return_pct": round(float(trades.mean()), 6) if len(trades) else 0.0,
        "holdout_profit_factor": round(float(wins.sum() / abs(losses.sum())), 6) if len(losses) and losses.sum() else None,
        "holdout_max_drawdown_pct": round(float(abs(drawdown.min())), 6) if len(drawdown) else 0.0,
        "holdout_returns_pct": [round(float(value), 6) for value in returns],
        "meta_holdout_observations": observations,
        **deflated_sharpe_ratio(returns, trials=3),
    }


def _feature_reference(X: list, feature_names: list[str]) -> dict:
    import numpy as np

    values = np.asarray(X, dtype=float)
    if values.ndim != 2 or not len(values):
        return {}
    result = {}
    for index, name in enumerate(feature_names):
        column = values[:, index]
        edges = np.unique(np.quantile(column, np.linspace(0, 1, 11)))
        if len(edges) < 3:
            continue
        edges[0], edges[-1] = -float("inf"), float("inf")
        counts, _ = np.histogram(column, bins=edges)
        result[name] = {
            "edges": [None if not np.isfinite(edge) else round(float(edge), 8) for edge in edges],
            "proportions": [round(float(value), 8) for value in (counts / max(1, counts.sum()))],
        }
    return result


def _candidate_metrics(row) -> dict:
    try:
        return json.loads(row.metrics_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _candidate_is_safe(metrics: dict) -> bool:
    from app.services.ml_activation import training_metrics_are_safe
    return training_metrics_are_safe(metrics)


def _candidate_utility(metrics: dict) -> float:
    return (
        float(metrics.get("holdout_avg_net_return_pct", 0.0))
        - 0.03 * float(metrics.get("holdout_max_drawdown_pct", 0.0))
        + 0.25 * float(metrics.get("f1", 0.0))
        + 0.10 * float(metrics.get("cpcv_f1_mean", 0.0) or 0.0)
        + 0.10 * float(metrics.get("deflated_sharpe_ratio", 0.0) or 0.0)
        - 0.10 * float(metrics.get("pbo", 0.0) or 0.0)
    )


def _beats_reference(candidate: dict, reference: dict) -> bool:
    return (
        _candidate_utility(candidate)
        >= _candidate_utility(reference) + settings.challenger_min_utility_gain
        and float(candidate.get("f1", 0.0)) >= float(reference.get("f1", 0.0)) - 0.03
        and float(candidate.get("holdout_max_drawdown_pct", 999.0))
        <= float(reference.get("holdout_max_drawdown_pct", 999.0)) + 5.0
    )


def train_champion_challengers(
    db: Session,
    *,
    target_name: str,
    asset_id: str | None,
    market: str | None = None,
) -> dict:
    """Trenuje czyste LR/RF/XGB i promuje tylko model lepszy po kosztach."""
    from sqlalchemy import select
    from app.db.models import MLModelRunORM
    from app.services.ml_models.registry import AVAILABLE_MODELS

    if asset_id is None and market is None:
        raise ValueError("Challenger suite requires asset_id or market")
    if target_name == "target_meta_label" and asset_id is not None:
        from app.services.meta_labeling import rebuild_oof_meta_labels
        rebuild_oof_meta_labels(db, asset_id)
    elif target_name == "target_meta_label" and market is not None:
        from app.services.meta_labeling import rebuild_oof_meta_labels
        from app.services.recommendation_calibration import market_segment
        for asset in list_assets(db):
            if market_segment(asset) == market:
                existing = list_training_rows_for_target(
                    db, "target_meta_label", asset_id=asset.id,
                )
                if not any(row.meta_label_source == "purged_oof_primary" for row in existing):
                    rebuild_oof_meta_labels(db, asset.id)

    model_names = [name for name in ("logistic_regression", "random_forest", "xgboost") if name in AVAILABLE_MODELS]
    if "logistic_regression" not in model_names:
        model_names.insert(0, "logistic_regression")
    candidates = []
    errors = {}
    for model_name in model_names:
        try:
            candidates.append(train_model(
                db, target_name=target_name, model_name=model_name,
                asset_id=asset_id, market=market, activate=False,
            ))
        except Exception as exc:
            errors[model_name] = str(exc)
    if not candidates:
        raise ValueError(f"Żaden challenger nie został wytrenowany: {errors}")

    from app.services.ml_validation import probability_of_backtest_overfitting
    pbo = probability_of_backtest_overfitting([_candidate_metrics(row) for row in candidates])
    for row in candidates:
        metrics = _candidate_metrics(row)
        metrics["pbo"] = pbo
        row.metrics_json = json.dumps(metrics, ensure_ascii=False)
    db.commit()

    baseline = next((row for row in candidates if row.model_name == "logistic_regression"), candidates[0])
    baseline_metrics = _candidate_metrics(baseline)
    safe_candidates = [row for row in candidates if _candidate_is_safe(_candidate_metrics(row))]
    winner = None
    if safe_candidates:
        best = max(safe_candidates, key=lambda row: _candidate_utility(_candidate_metrics(row)))
        if best.id == baseline.id:
            winner = baseline
        elif not _candidate_is_safe(baseline_metrics):
            winner = best
        else:
            best_metrics = _candidate_metrics(best)
            winner = best if _beats_reference(best_metrics, baseline_metrics) else baseline

    if asset_id is not None:
        previous = get_active_model_run(db, target_name, asset_id=asset_id)
    else:
        previous = db.scalar(select(MLModelRunORM).where(
            MLModelRunORM.target_name == target_name,
            MLModelRunORM.asset_id.is_(None),
            MLModelRunORM.market_segment == market,
            MLModelRunORM.is_active.is_(True),
        ).order_by(MLModelRunORM.trained_at.desc()).limit(1))
    if winner is None:
        for row in candidates:
            row.deployment_role = "rejected"
            row.promotion_reason = "Ujemna przewaga lub niewystarczający purged holdout"
        # Nie utrzymujemy starego championa, którego nie da się potwierdzić
        # obecną walidacją CPCV/DSR. Wtedy decyzję przejmie model rynku albo
        # pełnoprawna strefa „brak transakcji”.
        if previous is not None and not _candidate_is_safe(_candidate_metrics(previous)):
            previous.is_active = False
            previous.deployment_role = "archived"
            previous.promotion_reason = "Wycofany: brak potwierdzenia w aktualnej walidacji CPCV/DSR"
            previous = None
        db.commit()
        from app.services.meta_thresholds import invalidate_meta_threshold_cache
        invalidate_meta_threshold_cache(db)
        return {
            "champion_model": previous.model_name if previous else None,
            "champion_run_id": previous.id if previous else None,
            "promoted": False,
            "challenger_run_ids": [row.id for row in candidates],
            "errors": errors,
        }

    # Po pierwszym wdrożeniu kolejne cykle muszą pokonać działającego championa,
    # nie tylko świeżo wytrenowany baseline LR. Porównujemy wyłącznie metryki
    # policzone tą samą metodą purged temporal CV/holdout.
    if previous is not None:
        previous_metrics = _candidate_metrics(previous)
        comparable_incumbent = (
            previous_metrics.get("cv_method") == "purged_group_time_series"
            and _candidate_is_safe(previous_metrics)
        )
        if comparable_incumbent and not _beats_reference(_candidate_metrics(winner), previous_metrics):
            for row in candidates:
                row.deployment_role = "challenger"
                row.promotion_reason = "Nie pokonał aktywnego championa na porównywalnym purged holdout"
            db.commit()
            return {
                "champion_model": previous.model_name,
                "champion_run_id": previous.id,
                "promoted": False,
                "challenger_run_ids": [row.id for row in candidates],
                "errors": errors,
            }

    active_rows = db.scalars(select(MLModelRunORM).where(
        MLModelRunORM.target_name == target_name,
        MLModelRunORM.asset_id == asset_id if asset_id is not None else MLModelRunORM.asset_id.is_(None),
        MLModelRunORM.market_segment == market if market is not None else MLModelRunORM.market_segment.is_(None),
        MLModelRunORM.is_active.is_(True),
    )).all()
    for row in active_rows:
        row.is_active = False
        row.deployment_role = "archived"
    for row in candidates:
        row.is_active = row.id == winner.id
        row.deployment_role = "champion" if row.id == winner.id else "challenger"
        row.promotion_reason = (
            "Najlepsza dodatnia użyteczność na purged holdout po kosztach"
            if row.id == winner.id else "Nie pokonał championa na nietkniętym holdout"
        )
    db.commit()
    from app.services.meta_thresholds import invalidate_meta_threshold_cache
    invalidate_meta_threshold_cache(db)
    scored = score_asset(db, asset_id, target_name) if asset_id is not None else None
    return {
        "champion_model": winner.model_name,
        "champion_run_id": winner.id,
        "promoted": previous is None or previous.id != winner.id,
        "challenger_run_ids": [row.id for row in candidates if row.id != winner.id],
        "prediction_id": scored.id if scored else None,
        "market": market,
        "errors": errors,
    }


def run_backtest(db: Session, target_name: str = "target_up_5d", asset_id: str | None = None):
    import joblib
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    # Per-asset modele mają priorytet; uzupełnij globalnymi dla brakujących typów
    per_asset = get_all_active_model_runs(db, target_name, asset_id=asset_id)
    global_runs = get_all_active_model_runs(db, target_name, asset_id=None)
    per_asset_names = {r.model_name for r in per_asset}
    active_runs = list(per_asset) + [r for r in global_runs if r.model_name not in per_asset_names]
    if not active_runs:
        raise ValueError("No active model for target")

    rows = list_training_rows_for_target(db, target_name, asset_id=asset_id)
    if not rows:
        raise ValueError("No training rows for backtest")

    per_model_results = {}
    for active in active_runs:
        bundle = joblib.load(active.model_path)
        model = bundle["model"]
        feature_names = bundle["feature_names"]
        try:
            training_meta = json.loads(active.metrics_json)
        except (TypeError, ValueError):
            training_meta = {}
        train_end_raw = training_meta.get("train_end")
        if not train_end_raw:
            raise ValueError("Active model predates temporal holdout metadata; retrain it first")
        from datetime import datetime as _dt
        train_end = _dt.fromisoformat(train_end_raw)
        evaluation_rows = [r for r in rows if ensure_utc(r.snapshot_at) > ensure_utc(train_end)]
        if not evaluation_rows:
            raise ValueError("No out-of-sample rows newer than the model training window")
        X, y, _ = _xy(evaluation_rows, target_name, feature_names)
        preds = model.predict(X)
        probs = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else [0.5] * len(X)
        per_model_results[active.model_name] = {
            "accuracy":  float(accuracy_score(y, preds)),
            "precision": float(precision_score(y, preds, zero_division=0)),
            "recall":    float(recall_score(y, preds, zero_division=0)),
            "f1":        float(f1_score(y, preds, zero_division=0)),
            "avg_probability_up": float(mean(probs)) if len(probs) else 0.0,
            "is_global": active.asset_id is None,
            "out_of_sample_rows": len(evaluation_rows),
        }

    result = {
        "target_name": target_name,
        "asset_id": asset_id,
        "rows": min(v["out_of_sample_rows"] for v in per_model_results.values()),
        "models": per_model_results,
        # Metryki ensemble (średnia z modeli)
        "accuracy":  round(float(mean(v["accuracy"]  for v in per_model_results.values())), 4),
        "precision": round(float(mean(v["precision"] for v in per_model_results.values())), 4),
        "recall":    round(float(mean(v["recall"]    for v in per_model_results.values())), 4),
        "f1":        round(float(mean(v["f1"]        for v in per_model_results.values())), 4),
        "avg_probability_up": round(float(mean(v["avg_probability_up"] for v in per_model_results.values())), 4),
    }
    row = insert_backtest_result(db, active_runs[0].id, json.dumps(result, ensure_ascii=False))
    db.commit()
    db.refresh(row)
    return row


def score_asset(db: Session, asset_id: str, target_name: str = "target_up_5d"):
    from app.services.ml_models.registry import predict_proba_single
    from app.repositories.assets import get_asset
    from app.services.recommendation_calibration import market_segment

    # Priorytet: champion per-asset → wspólny champion rynku → globalny.
    per_asset = get_all_active_model_runs(db, target_name, asset_id=asset_id)
    asset = get_asset(db, asset_id)
    market = market_segment(asset) if asset is not None else "OTHER"
    market_runs = get_active_market_model_runs(db, target_name, market)
    global_runs = get_all_active_model_runs(db, target_name, asset_id=None)
    active_runs = list(per_asset or market_runs or global_runs)
    if not active_runs:
        return None

    vec, feature = _feature_vector(db, asset_id)
    if vec is None or feature is None:
        return None

    from app.services.meta_labeling import enrich_meta_features, live_primary_meta_features
    live_meta = None
    if target_name == "target_meta_label":
        live_meta = live_primary_meta_features(db, asset_id, vec)
        vec = enrich_meta_features(vec, live=live_meta)

    # Buduj historyczne X dla LSTM (ostatnie 25 wierszy + aktualny snapshot)
    hist_rows = list_training_rows_for_target(db, target_name, asset_id=asset_id)[-25:]
    X_full = [
        enrich_meta_features(json.loads(r.feature_json), row=r)
        if target_name == "target_meta_label" else json.loads(r.feature_json)
        for r in hist_rows
    ] + [vec]

    probs = []
    models_used = []
    for run in active_runs:
        try:
            p = predict_proba_single(run.model_name, run.model_path, X_full)
            probs.append(p)
            models_used.append(run.model_name)
        except Exception as exc:
            print(f"[ml] score_asset {run.model_name}: {exc}")

    if not probs:
        return None

    prob_up = float(mean(probs))
    if target_name == "target_meta_label":
        from app.services.meta_thresholds import calibrated_meta_threshold
        threshold = calibrated_meta_threshold(db, market, feature.regime_label)
        label = "trade" if prob_up >= threshold.threshold else "skip"
    elif target_name == "target_triple_barrier":
        label = "upper" if prob_up >= 0.5 else "lower"
    else:
        label = "up" if prob_up >= 0.5 else "down"
    row = insert_prediction(
        db,
        asset_id=asset_id,
        snapshot_at=feature.snapshot_at,
        model_run_id=active_runs[0].id,
        target_name=target_name,
        probability_up=prob_up,
        predicted_label=label,
        raw_json=json.dumps({
            "features": vec, "probability_up": prob_up,
            "models_used": models_used,
            "per_model_probs": dict(zip(models_used, probs)),
            "model_scope": "asset" if per_asset else "market" if market_runs else "global",
            "market": market,
            "meta_features": live_meta,
            "meta_threshold": threshold.threshold if target_name == "target_meta_label" else None,
            "meta_threshold_scope": threshold.scope if target_name == "target_meta_label" else None,
        }, ensure_ascii=False),
    )
    delete_predictions_older_than(db, settings.ml_prediction_retention_days)
    db.commit()
    db.refresh(row)
    return row


# Czytelne polskie nazwy cech do interpretacji tekstowej
_FEATURE_NAMES_PL: dict[str, str] = {
    "trend_score":           "trend",
    "sentiment_score":       "sentyment newsów",
    "divergence_score":      "dywergencja",
    "fragility_score":       "kruchość",
    "narrative_shift_score": "zmiana narracji",
    "volatility_10d":        "zmienność 10d",
    "momentum_20d":          "momentum 20d",
    "news_count_7d":         "aktywność newsowa",
    "price_change_1d_pct":   "zmiana ceny 1d",
    "price_change_5d_pct":   "zmiana ceny 5d",
    "price_change_20d_pct":  "zmiana ceny 20d",
    "rsi_14":                "RSI(14)",
    "macd_histogram":        "MACD histogram",
    "bb_pct":                "pozycja Bollinger",
    "volume_ratio_20d":      "wolumen vs średnia",
    "price_vs_52w_high":     "% od rocznego max",
    "above_sma200":          "powyżej SMA200",
    "spy_return_5d":         "zwrot SPY 5d",
    "alpha_vs_spy_5d":       "alpha vs SPY",
    # Nowe cechy XGBoost
    "day_of_week":           "dzień tygodnia",
    "days_to_earnings":      "dni do wyników",
    "iv_rank":               "ranga IV (opcje)",
    "rs_vs_sector_20d":      "siła vs sektor 20d",
    "poc_distance_pct":      "odległość od POC",
    "has_iv":                "dostępność danych opcyjnych",
    "has_upcoming_earnings": "znany termin wyników",
    "has_earnings":          "dostępność wyników",
    "days_since_earnings":   "dni od wyników",
    "eps_surprise_pct":      "zaskoczenie EPS",
    "revenue_surprise_pct":  "zaskoczenie przychodów",
    "has_pead_1d":           "dostępność PEAD 1d",
    "pead_return_1d_pct":    "reakcja po wynikach 1d",
    "has_pead_5d":           "dostępność PEAD 5d",
    "pead_return_5d_pct":    "dryf po wynikach 5d",
    "has_insider_90d":       "dostępność transakcji insiderów",
    "insider_net_value_log_90d": "saldo transakcji insiderów",
    "insider_buy_ratio_90d": "udział zakupów insiderów",
    "insider_cluster_buyers_90d": "grupowe zakupy insiderów",
    "days_since_insider_filing": "dni od zgłoszenia insidera",
    "has_short_interest":    "dostępność short interest",
    "short_percent_float":   "short jako część free float",
    "short_ratio":           "days-to-cover",
    "short_percent_change":  "zmiana short interest",
    "news_event_positive_7d": "pozytywne zdarzenia newsowe",
    "news_event_negative_7d": "negatywne zdarzenia newsowe",
    "news_event_earnings_guidance_7d": "newsy o wynikach i prognozach",
    "news_event_corporate_action_7d": "zdarzenia korporacyjne",
    "news_event_financing_7d": "newsy o finansowaniu",
    "news_event_legal_regulatory_7d": "ryzyko prawne i regulacyjne",
    "news_event_contract_product_7d": "kontrakty i produkty",
    "news_event_management_cyber_7d": "zarząd i cyberbezpieczeństwo",
    "news_attention_zscore_7d": "nietypowe natężenie newsów",
    "news_source_diversity_7d": "różnorodność źródeł newsów",
    "news_high_impact_7d": "newsy o wysokim wpływie",
    "news_nlp_coverage_7d": "pokrycie newsów przez NLP",
    "news_relevance_mean_7d": "trafność newsów dla aktywa",
    "news_sentiment_confidence_mean_7d": "pewność sentymentu newsów",
}


def _pl(feature_name: str) -> str:
    return _FEATURE_NAMES_PL.get(feature_name, feature_name)


def explain_prediction(
    db: Session,
    asset_id: str,
    target_name: str = "target_up_5d",
) -> MLExplanationResponse | None:
    """
    Wyjaśnienie predykcji ML dla konkretnego aktywa.

    Metoda: dla regresji logistycznej wkład każdej cechy do log-odds predykcji
    to coef[i] * feature_value[i]. Sumaryczny log-odds -> prawdopodobieństwo przez sigmoid.
    Nie wymaga SHAP ani dodatkowych zależności.
    """
    import joblib

    # Szukaj aktywnego modelu logistycznego do wyjaśnienia (ma coef_)
    # 1. Per-asset LR
    active = None
    for run in get_all_active_model_runs(db, target_name, asset_id=asset_id):
        if run.model_name == "logistic_regression":
            active = run
            break
    # 2. Globalny LR (asset_id IS NULL)
    if active is None:
        for run in get_all_active_model_runs(db, target_name, asset_id=None):
            if run.model_name == "logistic_regression":
                active = run
                break
    if active is None:
        return None

    vec, feature = _feature_vector(db, asset_id)
    if vec is None or feature is None:
        return None

    bundle = joblib.load(active.model_path)
    model = bundle["model"]
    explanation_model = bundle.get("base_model", model)
    feature_names: list[str] = bundle["feature_names"]

    # Pipeline: wyciągnij koeficjenty z kroku "clf" (tylko regresja logistyczna)
    clf = explanation_model.named_steps["clf"] if hasattr(explanation_model, "named_steps") else explanation_model
    if not hasattr(clf, "coef_"):
        return None
    coefs = clf.coef_[0]          # shape (n_features,)
    feature_values = [float(vec.get(name, 0.0)) for name in feature_names]

    # --- Globalna ważność cech (abs koeficjentów) ---
    importances = sorted(
        [
            MLFeatureImportance(
                feature=name,
                importance=round(abs(float(c)), 4),
                direction="bullish" if c > 0 else "bearish",
            )
            for name, c in zip(feature_names, coefs)
        ],
        key=lambda x: -x.importance,
    )

    # --- Wkłady dla tej konkretnej predykcji ---
    contributions = sorted(
        [
            MLPredictionContribution(
                feature=name,
                feature_value=round(val, 3),
                contribution=round(float(c) * val, 4),
                direction="bullish" if (float(c) * val) > 0 else "bearish",
            )
            for name, c, val in zip(feature_names, coefs, feature_values)
        ],
        key=lambda x: -abs(x.contribution),
    )

    # --- Prawdopodobieństwo ---
    X = [feature_values]
    prob_up = float(model.predict_proba(X)[0][1])
    is_positive = prob_up >= 0.5

    # --- Interpretacja tekstowa ---
    bull_drivers = [c for c in contributions if c.contribution > 0]
    bear_drivers = [c for c in contributions if c.contribution < 0]

    def _fmt_drivers(drivers: list, n: int = 3) -> str:
        return ", ".join(_pl(d.feature) for d in drivers[:n])

    if is_positive:
        top = _fmt_drivers(bull_drivers)
        brakes = _fmt_drivers(bear_drivers, 2)
        if target_name == "target_meta_label":
            interpretation = f"Model dopuszcza transakcję głównie przez: {top}."
        elif target_name == "target_triple_barrier":
            interpretation = f"Model wskazuje górną barierę głównie przez: {top}."
        else:
            interpretation = f"Model jest bullish głównie przez: {top}."
        if bear_drivers:
            interpretation += f" Czynniki hamujące: {brakes}."
    else:
        top = _fmt_drivers(bear_drivers)
        support = _fmt_drivers(bull_drivers, 2)
        if target_name == "target_meta_label":
            interpretation = f"Model odrzuca transakcję głównie przez: {top}."
        elif target_name == "target_triple_barrier":
            interpretation = f"Model wskazuje dolną barierę głównie przez: {top}."
        else:
            interpretation = f"Model jest bearish głównie przez: {top}."
        if bull_drivers:
            interpretation += f" Czynniki wspierające: {support}."

    if target_name == "target_meta_label":
        predicted_label = "trade" if is_positive else "skip"
    elif target_name == "target_triple_barrier":
        predicted_label = "upper" if is_positive else "lower"
    else:
        predicted_label = "up" if is_positive else "down"

    return MLExplanationResponse(
        asset_id=asset_id,
        target_name=target_name,
        probability_up=round(prob_up, 4),
        predicted_label=predicted_label,
        interpretation=interpretation,
        feature_importances=importances,
        prediction_contributions=contributions,
    )
