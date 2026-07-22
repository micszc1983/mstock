from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import ml_backtest_to_schema, ml_model_run_to_schema, ml_prediction_to_schema
from app.repositories.assets import get_asset
from app.repositories.ml import get_latest_prediction, list_backtest_results, list_model_runs, get_all_active_model_runs
from app.schemas.ml import (
    MLBacktestResponse,
    MLDatasetBuildResponse,
    MLDatasetStatsResponse,
    MLExplanationResponse,
    MLModeUpdate,
    MLModelRunResponse,
    MLPredictionResponse,
    MLStatusResponse,
    MLTrainRequest,
    MLMonitorResponse,
)
from app.services.ml_foundation import build_training_dataset, dataset_stats, explain_prediction, run_backtest, score_asset, set_ml_mode, status, train_model, train_all_targets, train_champion_challengers
from app.services.ml_models.registry import AVAILABLE_MODELS

router = APIRouter(tags=["ml"])


@router.get("/ml/status", response_model=MLStatusResponse)
def get_ml_status(db: Session = Depends(get_db)) -> MLStatusResponse:
    return status(db)


@router.post("/ml/mode", response_model=MLStatusResponse)
def set_mode(payload: MLModeUpdate, db: Session = Depends(get_db)) -> MLStatusResponse:
    """Awaryjny kill switch; true removes the block but never forces unsafe ML."""
    set_ml_mode(db, payload.ml_enabled)
    return status(db)


@router.post("/ml/dataset/build", response_model=MLDatasetBuildResponse)
def build_dataset(db: Session = Depends(get_db)) -> MLDatasetBuildResponse:
    return build_training_dataset(db)


@router.get("/ml/dataset/stats", response_model=MLDatasetStatsResponse)
def get_dataset_stats(db: Session = Depends(get_db)) -> MLDatasetStatsResponse:
    return dataset_stats(db)


@router.post("/ml/features/ablation")
def feature_ablation(
    target_name: str = "target_up_5d",
    asset_id: str | None = None,
    market: str | None = None,
    approve: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Purged-CV feature ablation; diagnostic only, never promotes a model."""
    if asset_id is not None and get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    try:
        from app.services.feature_ablation import run_feature_ablation
        return run_feature_ablation(
            db, target_name=target_name, asset_id=asset_id, market=market,
            approve=approve,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ml/models/train", response_model=MLModelRunResponse)
def train(payload: MLTrainRequest, db: Session = Depends(get_db)) -> MLModelRunResponse:
    try:
        row = train_model(db, target_name=payload.target_name, model_name=payload.model_name,
                          asset_id=payload.asset_id, use_optuna=payload.use_optuna,
                          optuna_trials=payload.optuna_trials, activate=payload.promote,
                          market=payload.market_segment)
        return ml_model_run_to_schema(row)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Błąd treningu: {exc}")


@router.post("/ml/models/train-all")
def train_all(db: Session = Depends(get_db)) -> list[dict]:
    """Trenuje wszystkie dostępne typy modeli dla każdego aktywa × targetu."""
    try:
        return train_all_targets(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Błąd treningu: {exc}")


@router.post("/ml/models/train-challengers")
def train_challengers(
    asset_id: str | None = None,
    market: str | None = None,
    target_name: str = "target_meta_label",
    db: Session = Depends(get_db),
) -> dict:
    if asset_id is None and market not in {"GPW", "USA"}:
        raise HTTPException(status_code=422, detail="Podaj asset_id albo market=GPW/USA")
    if asset_id is not None and get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    try:
        return train_champion_challengers(
            db, target_name=target_name, asset_id=asset_id, market=market,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/ml/models/available")
def available_models() -> dict:
    """Zwraca listę dostępnych typów modeli (zainstalowane pakiety)."""
    return {"available": AVAILABLE_MODELS}


@router.post("/ml/monitor/run", response_model=list[MLMonitorResponse])
def run_monitoring(db: Session = Depends(get_db)):
    from app.services.ml_monitoring import monitor_active_models
    return monitor_active_models(db, allow_rollback=True)


@router.get("/ml/monitor", response_model=list[MLMonitorResponse])
def monitoring(limit: int = 200, db: Session = Depends(get_db)):
    from app.services.ml_monitoring import latest_monitoring
    return latest_monitoring(db, limit=min(max(limit, 1), 1000))


@router.get("/ml/models/comparison")
def model_comparison(target_name: str = "target_up_5d", db: Session = Depends(get_db)) -> list[dict]:
    """
    Zwraca porównanie metryk dla wszystkich aktywnych modeli,
    pogrupowane po aktywie i typie modelu.
    """
    import json as _json
    from app.repositories.assets import list_assets
    from app.schemas.ml import ML_TARGETS

    from sqlalchemy import select
    from app.db.models import MLModelRunORM

    from app.services.recommendation_calibration import market_segment

    def recent_runs(asset_id: str | None, market: str | None = None) -> list:
        stmt = select(MLModelRunORM).where(
            MLModelRunORM.target_name == target_name,
            MLModelRunORM.deployment_role.in_(("champion", "challenger", "candidate", "rejected")),
        )
        if asset_id is not None:
            stmt = stmt.where(MLModelRunORM.asset_id == asset_id)
        else:
            stmt = stmt.where(
                MLModelRunORM.asset_id.is_(None),
                MLModelRunORM.market_segment == market if market is not None
                else MLModelRunORM.market_segment.is_(None),
            )
        stmt = stmt.order_by(MLModelRunORM.trained_at.desc()).limit(20)
        unique = {}
        for run in db.scalars(stmt).all():
            unique.setdefault(run.model_name, run)
        return list(unique.values())

    global_runs = recent_runs(None)
    global_by_name = {r.model_name: r for r in global_runs}

    result = []
    for asset in list_assets(db):
        per_asset = recent_runs(asset.id)
        per_asset_names = {r.model_name for r in per_asset}
        market_runs = recent_runs(None, market_segment(asset))
        market_by_name = {r.model_name: r for r in market_runs}
        # Per-asset ma priorytet, potem wspólny model rynku, na końcu globalny.
        fallback = {**global_by_name, **market_by_name}
        runs = list(per_asset) + [r for name, r in fallback.items() if name not in per_asset_names]
        for run in runs:
            try:
                metrics = _json.loads(run.metrics_json)
            except Exception:
                metrics = {}
            result.append({
                "asset_id": asset.id,
                "asset_name": asset.name,
                "model_name": run.model_name,
                "target_name": run.target_name,
                "accuracy": metrics.get("accuracy", 0.0),
                "precision": metrics.get("precision", 0.0),
                "recall": metrics.get("recall", 0.0),
                "f1": metrics.get("f1", 0.0),
                "avg_probability_up": metrics.get("avg_probability_up", 0.5),
                "train_rows": metrics.get("train_rows", run.dataset_rows),
                "trained_at": run.trained_at.isoformat() if run.trained_at else None,
                "is_global": run.asset_id is None,
                "market_segment": run.market_segment,
                "deployment_role": run.deployment_role,
                "promotion_reason": run.promotion_reason,
                "holdout_avg_net_return_pct": metrics.get("holdout_avg_net_return_pct"),
                "holdout_profit_factor": metrics.get("holdout_profit_factor"),
                "holdout_max_drawdown_pct": metrics.get("holdout_max_drawdown_pct"),
                "holdout_win_rate_pct": metrics.get("holdout_win_rate_pct"),
                "cv_method": metrics.get("cv_method"),
                "cv_purge_sessions": metrics.get("cv_purge_sessions"),
                # Purged temporal CV
                "cv_accuracy_mean": metrics.get("cv_accuracy_mean"),
                "cv_accuracy_std":  metrics.get("cv_accuracy_std"),
                "cv_f1_mean":       metrics.get("cv_f1_mean"),
                "cv_f1_std":        metrics.get("cv_f1_std"),
                "cv_folds":         metrics.get("cv_folds"),
                "calibration_method": metrics.get("calibration_method"),
                "calibration_ece": metrics.get("calibration_ece"),
                "cpcv_f1_mean": metrics.get("cpcv_f1_mean"),
                "cpcv_paths": metrics.get("cpcv_paths"),
                "pbo": metrics.get("pbo"),
                "deflated_sharpe_ratio": metrics.get("deflated_sharpe_ratio"),
                # Optuna
                "optuna_best_params": metrics.get("optuna_best_params"),
            })
    return result


@router.get("/ml/models", response_model=list[MLModelRunResponse])
def models(db: Session = Depends(get_db)) -> list[MLModelRunResponse]:
    return [ml_model_run_to_schema(row) for row in list_model_runs(db)]


@router.post("/ml/backtests/run", response_model=MLBacktestResponse)
def backtest(target_name: str = "target_up_5d", asset_id: str | None = None, db: Session = Depends(get_db)) -> MLBacktestResponse:
    try:
        row = run_backtest(db, target_name=target_name, asset_id=asset_id)
        return ml_backtest_to_schema(row)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Błąd backtestingu: {exc}")


@router.get("/ml/backtests", response_model=list[MLBacktestResponse])
def backtests(db: Session = Depends(get_db)) -> list[MLBacktestResponse]:
    return [ml_backtest_to_schema(row) for row in list_backtest_results(db)]


@router.post("/assets/{asset_id}/ml/score", response_model=MLPredictionResponse)
def score(asset_id: str, target_name: str = "target_up_5d", db: Session = Depends(get_db)) -> MLPredictionResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    row = score_asset(db, asset_id, target_name=target_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Could not score {asset_id}")
    return ml_prediction_to_schema(row)


@router.get("/assets/{asset_id}/ml/prediction/latest", response_model=MLPredictionResponse)
def latest_prediction(asset_id: str, target_name: str = "target_up_5d", db: Session = Depends(get_db)) -> MLPredictionResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    row = get_latest_prediction(db, asset_id, target_name)
    if row is None:
        row = score_asset(db, asset_id, target_name=target_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No prediction for {asset_id}")
    return ml_prediction_to_schema(row)

@router.get("/assets/{asset_id}/ml/explain", response_model=MLExplanationResponse)
def explain(
    asset_id: str,
    target_name: str = "target_up_5d",
    db: Session = Depends(get_db),
) -> MLExplanationResponse:
    result = explain_prediction(db, asset_id, target_name)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No active model or no feature snapshot for this asset.")
    return result
