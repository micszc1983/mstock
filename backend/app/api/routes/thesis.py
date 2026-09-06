from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import asset_to_schema, price_to_schema, thesis_outcome_to_schema, thesis_to_schema
from app.repositories.assets import get_asset
from app.repositories.prices import list_prices
from app.repositories.outcomes import list_outcomes_for_asset, list_outcomes_for_thesis
from app.repositories.theses import get_latest_thesis, list_thesis_history
from app.schemas.news import NarrativePoint
from app.schemas.outcomes import ThesisOutcomeResponse
from app.schemas.thesis import BreakMonitorResponse, StoredThesisResponse, ThesisResponse
from app.services.analytics import build_break_monitor, build_narrative_history, make_thesis
from app.services.feature_builder import rebuild_asset_features_and_forecasts
from app.services.outcome_evaluator import evaluate_asset_outcomes, evaluate_thesis_outcomes
from app.services.news_features import list_news_for_analysis

router = APIRouter(tags=["thesis"])


def _load_asset_bundle(db: Session, asset_id: str):
    row = get_asset(db, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    asset = asset_to_schema(row)
    prices = [price_to_schema(p) for p in list_prices(db, asset_id)]
    news = list_news_for_analysis(db, asset_id)
    return row, asset, prices, news


@router.get("/assets/{asset_id}/thesis", response_model=ThesisResponse)
def get_thesis(asset_id: str, db: Session = Depends(get_db)) -> ThesisResponse:
    _, asset, prices, news = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    return make_thesis(asset, prices, news)


@router.get("/assets/{asset_id}/theses/latest", response_model=StoredThesisResponse)
def get_latest_saved_thesis(asset_id: str, db: Session = Depends(get_db)) -> StoredThesisResponse:
    row, _, prices, _ = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    thesis_row = get_latest_thesis(db, asset_id)
    if thesis_row is None:
        rebuild_asset_features_and_forecasts(db, row)
        thesis_row = get_latest_thesis(db, asset_id)
        if thesis_row is None:
            raise HTTPException(status_code=404, detail=f"Could not build thesis for {asset_id}")
    return thesis_to_schema(thesis_row)


@router.get("/assets/{asset_id}/theses/history", response_model=list[StoredThesisResponse])
def get_saved_thesis_history(asset_id: str, limit: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db)) -> list[StoredThesisResponse]:
    row, _, prices, _ = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    thesis_rows = list_thesis_history(db, asset_id, limit=limit)
    if not thesis_rows:
        rebuild_asset_features_and_forecasts(db, row)
        thesis_rows = list_thesis_history(db, asset_id, limit=limit)
    return [thesis_to_schema(item) for item in thesis_rows]


@router.get("/assets/{asset_id}/break-monitor", response_model=BreakMonitorResponse)
def get_break_monitor(asset_id: str, db: Session = Depends(get_db)) -> BreakMonitorResponse:
    _, asset, prices, news = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    return build_break_monitor(asset, prices, news)


@router.get("/assets/{asset_id}/narratives", response_model=list[NarrativePoint])
def get_narratives(asset_id: str, days: int = Query(default=7, ge=3, le=30), db: Session = Depends(get_db)) -> list[NarrativePoint]:
    _, _, _, news = _load_asset_bundle(db, asset_id)
    return build_narrative_history(news, days=days)


@router.post("/assets/{asset_id}/thesis-outcomes/rebuild")
def rebuild_thesis_outcomes(asset_id: str, limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> dict[str, int | str]:
    row, _, prices, _ = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    created = evaluate_asset_outcomes(db, asset_id, limit=limit)
    return {"asset_id": asset_id, "evaluated": created}


@router.get("/assets/{asset_id}/thesis-outcomes/history", response_model=list[ThesisOutcomeResponse])
def get_thesis_outcomes_history(asset_id: str, limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[ThesisOutcomeResponse]:
    row, _, prices, _ = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    outcomes = list_outcomes_for_asset(db, asset_id, limit=limit)
    if not outcomes:
        evaluate_asset_outcomes(db, asset_id, limit=limit)
        outcomes = list_outcomes_for_asset(db, asset_id, limit=limit)
    return [thesis_outcome_to_schema(item) for item in outcomes]


@router.get("/assets/{asset_id}/theses/{thesis_id}/outcomes", response_model=list[ThesisOutcomeResponse])
def get_outcomes_for_single_thesis(asset_id: str, thesis_id: int, db: Session = Depends(get_db)) -> list[ThesisOutcomeResponse]:
    row, _, prices, _ = _load_asset_bundle(db, asset_id)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for {asset_id}")
    outcomes = list_outcomes_for_thesis(db, thesis_id)
    if not outcomes:
        thesis_row = next((item for item in list_thesis_history(db, asset_id, limit=500) if item.id == thesis_id), None)
        if thesis_row is None:
            raise HTTPException(status_code=404, detail=f"Unknown thesis id: {thesis_id}")
        evaluate_thesis_outcomes(db, thesis_row)
        outcomes = list_outcomes_for_thesis(db, thesis_id)
    return [thesis_outcome_to_schema(item) for item in outcomes]
