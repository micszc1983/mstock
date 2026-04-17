from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import strategy_comparison_to_schema, walkforward_backtest_to_schema
from app.repositories.assets import get_asset
from app.repositories.evaluation import get_latest_strategy_comparison, list_strategy_comparisons
from app.schemas.evaluation import StrategyComparisonResponse, WalkForwardBacktestResponse
from app.services.evaluation import compare_heuristic_vs_ml_for_asset, run_walkforward_backtest

router = APIRouter(tags=["evaluation"])


@router.post("/ml/backtests/walkforward", response_model=WalkForwardBacktestResponse)
def walkforward_backtest(
    target_name: str = "target_up_5d",
    asset_id: str | None = None,
    db: Session = Depends(get_db),
) -> WalkForwardBacktestResponse:
    row = run_walkforward_backtest(db, target_name=target_name, asset_id=asset_id)
    return walkforward_backtest_to_schema(row)


@router.post("/assets/{asset_id}/evaluation/compare", response_model=StrategyComparisonResponse)
def compare_modes(asset_id: str, db: Session = Depends(get_db)) -> StrategyComparisonResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    row = compare_heuristic_vs_ml_for_asset(db, asset_id)
    return strategy_comparison_to_schema(row)


@router.get("/assets/{asset_id}/evaluation/latest", response_model=StrategyComparisonResponse)
def latest_comparison(asset_id: str, db: Session = Depends(get_db)) -> StrategyComparisonResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    row = get_latest_strategy_comparison(db, asset_id)
    if row is None:
        row = compare_heuristic_vs_ml_for_asset(db, asset_id)
    return strategy_comparison_to_schema(row)


@router.get("/evaluation/comparisons", response_model=list[StrategyComparisonResponse])
def comparisons(db: Session = Depends(get_db)) -> list[StrategyComparisonResponse]:
    return [strategy_comparison_to_schema(row) for row in list_strategy_comparisons(db)]
