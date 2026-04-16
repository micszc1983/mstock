from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import ml_backtest_to_schema, ml_model_run_to_schema, ml_prediction_to_schema
from app.repositories.assets import get_asset
from app.repositories.ml import get_latest_prediction, list_backtest_results, list_model_runs
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
)
from app.services.ml_foundation import build_training_dataset, dataset_stats, explain_prediction, run_backtest, score_asset, set_ml_mode, status, train_model, train_all_targets

router = APIRouter(tags=["ml"])


@router.get("/ml/status", response_model=MLStatusResponse)
def get_ml_status(db: Session = Depends(get_db)) -> MLStatusResponse:
    return status(db)


@router.post("/ml/mode", response_model=MLStatusResponse)
def set_mode(payload: MLModeUpdate, db: Session = Depends(get_db)) -> MLStatusResponse:
    set_ml_mode(db, payload.ml_enabled)
    return status(db)


@router.post("/ml/dataset/build", response_model=MLDatasetBuildResponse)
def build_dataset(db: Session = Depends(get_db)) -> MLDatasetBuildResponse:
    return build_training_dataset(db)


@router.get("/ml/dataset/stats", response_model=MLDatasetStatsResponse)
def get_dataset_stats(db: Session = Depends(get_db)) -> MLDatasetStatsResponse:
    return dataset_stats(db)


@router.post("/ml/models/train", response_model=MLModelRunResponse)
def train(payload: MLTrainRequest, db: Session = Depends(get_db)) -> MLModelRunResponse:
    try:
        row = train_model(db, target_name=payload.target_name, model_name=payload.model_name)
        return ml_model_run_to_schema(row)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Błąd treningu: {exc}")


@router.post("/ml/models/train-all")
def train_all(db: Session = Depends(get_db)) -> list[dict]:
    """Trenuje modele dla wszystkich obsługiwanych targetów."""
    try:
        return train_all_targets(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Błąd treningu: {exc}")


@router.get("/ml/models", response_model=list[MLModelRunResponse])
def models(db: Session = Depends(get_db)) -> list[MLModelRunResponse]:
    return [ml_model_run_to_schema(row) for row in list_model_runs(db)]


@router.post("/ml/backtests/run", response_model=MLBacktestResponse)
def backtest(target_name: str = "target_up_5d", db: Session = Depends(get_db)) -> MLBacktestResponse:
    try:
        row = run_backtest(db, target_name=target_name)
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

