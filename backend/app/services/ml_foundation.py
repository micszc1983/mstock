from __future__ import annotations

import json
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
    get_all_active_model_runs,
    get_latest_prediction,
    get_setting,
    insert_backtest_result,
    insert_model_run,
    insert_prediction,
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
    setting = get_setting(db, "ml_enabled")
    if setting is None:
        upsert_setting(db, "ml_enabled", "true" if settings.ml_enabled_default else "false")
        db.commit()
        return settings.ml_enabled_default
    return setting.setting_value.lower() == "true"


def set_ml_mode(db: Session, enabled: bool) -> bool:
    upsert_setting(db, "ml_enabled", "true" if enabled else "false")
    db.commit()
    return enabled


def _models_dir() -> Path:
    path = Path(settings.ml_models_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    # Załaduj ostatnie 260 cen (wystarczy na SMA200 + wskaźniki)
    all_prices = sorted(
        [price_to_schema(p) for p in list_prices(db, asset_id)],
        key=lambda p: ensure_utc(p.timestamp)
    )[-260:]

    closes  = [p.close  for p in all_prices]
    volumes = [p.volume for p in all_prices]

    snap_date = ensure_utc(feature.snapshot_at).date()
    spy_returns = fetch_spy_returns(settings.twelvedata_api_key) if settings.twelvedata_api_key else {}
    macro_data  = fetch_macro_data()

    # Ceny sektora ETF
    sector_closes: list = []
    sector_etf = _SECTOR_ETF_MAP.get(asset_id)
    if sector_etf:
        sector_prices = sorted(
            [price_to_schema(p) for p in list_prices(db, sector_etf)],
            key=lambda p: ensure_utc(p.timestamp)
        )[-260:]
        sector_closes = [p.close for p in sector_prices]

    tech = compute_all(closes, volumes, spy_returns, snap_date, asset_return_5d=None,
                       macro_data=macro_data, sector_closes=sector_closes)

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
    }
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

    built = 0
    for asset in list_assets(db):
        # Wczytaj wszystkie ceny posortowane chronologicznie
        all_prices = sorted(
            [price_to_schema(p) for p in list_prices(db, asset.id)],
            key=lambda p: ensure_utc(p.timestamp)
        )
        if len(all_prices) < 5:
            continue

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

            # Wskaźniki techniczne obliczane z okna cenowego do snap_date
            window_closes  = all_closes[:idx + 1]
            window_volumes = all_volumes[:idx + 1]
            tech = compute_all(window_closes, window_volumes, spy_returns, snap_date, ret_5d,
                               macro_data=macro_data, sector_closes=sector_closes)

            vec = {**base_vec, **tech}

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
    rows = list_training_rows(db)
    assets = {}
    for row in rows:
        assets[row.asset_id] = assets.get(row.asset_id, 0) + 1
    return MLDatasetStatsResponse(
        total_rows=len(rows),
        assets=assets,
        labeled_rows_1d=sum(1 for r in rows if r.target_up_1d is not None),
        labeled_rows_5d=sum(1 for r in rows if r.target_up_5d is not None),
        labeled_rows_20d=sum(1 for r in rows if r.target_up_20d is not None),
        thesis_success_rows=sum(1 for r in rows if r.target_thesis_success is not None),
    )


def status(db: Session) -> MLStatusResponse:
    enabled = get_ml_mode(db)
    total = count_training_rows(db)

    # Zbierz stan dla każdego targetu
    target_states: list[MLActiveModel] = []
    first_active = None
    for target in ML_TARGETS:
        active = get_active_model_run(db, target)
        if active and first_active is None:
            first_active = active
        labeled = _count_labeled(db, target)
        target_states.append(MLActiveModel(
            target_name=target,
            target_label=ML_TARGET_LABELS.get(target, target),
            model_name=active.model_name if active else None,
            is_trained=active is not None,
            dataset_rows=labeled,
        ))

    return MLStatusResponse(
        ml_mode="ml" if enabled else "heuristic",
        ml_enabled=enabled,
        active_model_name=first_active.model_name if first_active else None,
        active_target_name=first_active.target_name if first_active else None,
        dataset_rows=total,
        min_training_rows=settings.ml_min_training_rows,
        ready_for_training=total >= settings.ml_min_training_rows,
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
    """
    Trenuje wszystkie dostępne typy modeli dla każdego aktywa × targetu.
    Każdy model (LR, RF, XGBoost, LSTM) trenowany niezależnie — aktywne równolegle.
    """
    from app.services.ml_models.registry import AVAILABLE_MODELS
    results = []
    assets = list_assets(db)
    models_to_train = AVAILABLE_MODELS if AVAILABLE_MODELS else ["logistic_regression"]
    print(f"[ml] Trenowanie modeli: {models_to_train}")

    for model_name in models_to_train:
        for asset in assets:
            for target in ML_TARGETS:
                rows = list_training_rows_for_target(db, target, asset_id=asset.id)
                if len(rows) < settings.ml_min_training_rows:
                    results.append({
                        "model": model_name, "asset": asset.id, "target": target,
                        "skipped": True,
                        "reason": f"za mało danych: {len(rows)}/{settings.ml_min_training_rows}",
                    })
                    continue
                try:
                    row = train_model(db, target_name=target, model_name=model_name, asset_id=asset.id)
                    results.append({
                        "model": model_name, "asset": asset.id, "target": target,
                        "skipped": False, "model_run_id": row.id, "dataset_rows": row.dataset_rows,
                    })
                except Exception as exc:
                    results.append({
                        "model": model_name, "asset": asset.id, "target": target,
                        "skipped": True, "reason": str(exc),
                    })
    return results


def _xy(rows, target_name: str):
    X, y = [], []
    feature_names = None
    for row in rows:
        features = json.loads(row.feature_json)
        feature_names = list(features.keys())
        X.append([float(features[k]) for k in feature_names])
        y.append(int(getattr(row, target_name)))
    return X, y, feature_names or []


def train_model(
    db: Session,
    target_name: str = "target_up_5d",
    model_name: str = "logistic_regression",
    asset_id: str | None = None,
    use_optuna: bool = False,
    optuna_trials: int = 30,
):
    from app.services.ml_models.registry import (
        train_single_model as _train_single,
        cv_score_model as _cv_score,
        optimize_model as _optimize,
    )

    rows = list_training_rows_for_target(db, target_name, asset_id=asset_id)
    if len(rows) < settings.ml_min_training_rows:
        raise ValueError(f"Not enough rows to train. Need at least {settings.ml_min_training_rows}, got {len(rows)}")

    X_all, y_all, feature_names = _xy(rows, target_name)

    # ── 1. Optuna hyperparameter search (opcjonalne) ─────────────────────────
    best_params: dict | None = None
    optuna_result: dict = {}
    if use_optuna:
        print(f"[ml] Optuna search: {model_name}/{target_name} ({optuna_trials} trials)…")
        best_params = _optimize(model_name, X_all, y_all, n_trials=optuna_trials)
        if best_params:
            print(f"[ml] Optuna best params: {best_params}")
            optuna_result = {"optuna_best_params": best_params, "optuna_trials": optuna_trials}

    # ── 2. Trenuj model finalny na podziale 80/20 ────────────────────────────
    split = max(int(len(rows) * 0.8), 1)
    train_rows = rows[:split]
    test_rows  = rows[split:] if split < len(rows) else rows[-max(1, len(rows) // 5):]
    X_train, y_train, _ = _xy(train_rows, target_name)
    X_test,  y_test,  _ = _xy(test_rows,  target_name)

    asset_suffix = f"_{asset_id}" if asset_id else ""
    model_path = _models_dir() / f"{model_name}_{target_name}{asset_suffix}.joblib"

    model_metrics = _train_single(
        model_name, X_train, y_train, X_test, y_test, feature_names,
        str(model_path), best_params=best_params,
    )

    # ── 3. Stratified K-Fold CV na całym datasecie ───────────────────────────
    cv_metrics: dict = {}
    try:
        cv_result = _cv_score(model_name, X_all, y_all, feature_names,
                              n_splits=5, best_params=best_params)
        if cv_result:
            cv_metrics = cv_result
            print(f"[ml] CV {model_name}: acc={cv_result['cv_accuracy_mean']:.3f}±{cv_result['cv_accuracy_std']:.3f}  "
                  f"f1={cv_result['cv_f1_mean']:.3f}±{cv_result['cv_f1_std']:.3f}")
    except Exception as exc:
        print(f"[ml] CV skipped: {exc}")

    metrics = {
        **model_metrics,
        **cv_metrics,
        **optuna_result,
        "train_rows": len(train_rows),
        "test_rows":  len(test_rows),
        "feature_names": feature_names,
        "asset_id": asset_id,
    }

    row = insert_model_run(
        db, model_name=model_name, target_name=target_name,
        dataset_rows=len(rows), metrics_json=json.dumps(metrics, ensure_ascii=False),
        model_path=str(model_path), is_active=True, asset_id=asset_id,
    )
    db.commit()
    db.refresh(row)
    return row


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
        X, y = [], []
        for row in rows:
            features = json.loads(row.feature_json)
            X.append([float(features.get(k, 0.0)) for k in feature_names])
            y.append(int(getattr(row, target_name)))
        preds = model.predict(X)
        probs = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else [0.5] * len(X)
        per_model_results[active.model_name] = {
            "accuracy":  float(accuracy_score(y, preds)),
            "precision": float(precision_score(y, preds, zero_division=0)),
            "recall":    float(recall_score(y, preds, zero_division=0)),
            "f1":        float(f1_score(y, preds, zero_division=0)),
            "avg_probability_up": float(mean(probs)) if len(probs) else 0.0,
            "is_global": active.asset_id is None,
        }

    result = {
        "target_name": target_name,
        "asset_id": asset_id,
        "rows": len(rows),
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

    # Zbierz per-asset modele i uzupełnij globalnymi dla brakujących typów
    per_asset = get_all_active_model_runs(db, target_name, asset_id=asset_id)
    global_runs = get_all_active_model_runs(db, target_name, asset_id=None)
    per_asset_names = {r.model_name for r in per_asset}
    # Per-asset ma priorytet; globalny używany tylko jeśli brak per-asset dla danego modelu
    active_runs = list(per_asset) + [r for r in global_runs if r.model_name not in per_asset_names]
    if not active_runs:
        return None

    vec, feature = _feature_vector(db, asset_id)
    if vec is None or feature is None:
        return None

    # Buduj historyczne X dla LSTM (ostatnie 25 wierszy + aktualny snapshot)
    hist_rows = list_training_rows_for_target(db, target_name, asset_id=asset_id)[-25:]
    X_full = [json.loads(r.feature_json) for r in hist_rows] + [vec]

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
        }, ensure_ascii=False),
    )
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
    feature_names: list[str] = bundle["feature_names"]

    # Pipeline: wyciągnij koeficjenty z kroku "clf" (tylko regresja logistyczna)
    clf = model.named_steps["clf"] if hasattr(model, "named_steps") else model
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
    is_bullish = prob_up >= 0.5

    # --- Interpretacja tekstowa ---
    bull_drivers = [c for c in contributions if c.contribution > 0]
    bear_drivers = [c for c in contributions if c.contribution < 0]

    def _fmt_drivers(drivers: list, n: int = 3) -> str:
        return ", ".join(_pl(d.feature) for d in drivers[:n])

    if is_bullish:
        top = _fmt_drivers(bull_drivers)
        brakes = _fmt_drivers(bear_drivers, 2)
        interpretation = f"Model jest bullish głównie przez: {top}."
        if bear_drivers:
            interpretation += f" Czynniki hamujące: {brakes}."
    else:
        top = _fmt_drivers(bear_drivers)
        support = _fmt_drivers(bull_drivers, 2)
        interpretation = f"Model jest bearish głównie przez: {top}."
        if bull_drivers:
            interpretation += f" Czynniki wspierające: {support}."

    return MLExplanationResponse(
        asset_id=asset_id,
        target_name=target_name,
        probability_up=round(prob_up, 4),
        predicted_label="up" if is_bullish else "down",
        interpretation=interpretation,
        feature_importances=importances,
        prediction_contributions=contributions,
    )
