from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recommendation import AssetRecommendation, RecommendationJournalRecord, TopPick
from app.services.recommendation_engine import build_all_recommendations, build_recommendation, build_top_picks

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=list[AssetRecommendation])
def get_all_recommendations(db: Session = Depends(get_db)) -> list[AssetRecommendation]:
    """Kosztowo i historycznie kalibrowane decyzje dla wszystkich aktywów."""
    return build_all_recommendations(db)


@router.get("/top-picks", response_model=list[TopPick])
def get_top_picks(db: Session = Depends(get_db)) -> list[TopPick]:
    """Aktywa z maksymalną zbieżnością wszystkich sygnałów bullish."""
    return build_top_picks(db)


@router.get("/recommendations/journal", response_model=list[RecommendationJournalRecord])
def get_recommendation_journal(
    limit: int = Query(200, ge=1, le=1000),
    asset_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[RecommendationJournalRecord]:
    from app.services.recommendation_journal import list_recommendation_records
    return list_recommendation_records(db, limit=limit, asset_id=asset_id)


@router.get("/recommendations/audit/latest")
def get_latest_recommendation_audit(db: Session = Depends(get_db)) -> dict:
    from fastapi import HTTPException
    from app.services.recommendation_audit import latest_audit
    result = latest_audit(db)
    if result is None:
        raise HTTPException(status_code=404, detail="Audyt nie został jeszcze uruchomiony.")
    return result


@router.post("/admin/recommendations/audit")
def run_recommendation_audit(
    folds: int = Query(3, ge=2, le=5),
    db: Session = Depends(get_db),
) -> dict:
    from fastapi import HTTPException
    from app.services.recommendation_audit import run_walk_forward_audit
    try:
        return run_walk_forward_audit(db, fold_count=folds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/admin/recommendations/journal/snapshot")
def snapshot_recommendations(db: Session = Depends(get_db)) -> dict:
    from app.services.recommendation_journal import (
        evaluate_recommendation_outcomes,
        persist_current_recommendations,
    )
    evaluated = evaluate_recommendation_outcomes(db)
    inserted = persist_current_recommendations(db)
    return {"inserted": inserted, "evaluated": evaluated}


@router.get("/assets/{asset_id}/recommendation", response_model=AssetRecommendation)
def get_asset_recommendation(asset_id: str, db: Session = Depends(get_db)) -> AssetRecommendation:
    """Szczegółowa rekomendacja dla jednego aktywa."""
    from fastapi import HTTPException
    result = build_recommendation(db, asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return result
