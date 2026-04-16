from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recommendation import AssetRecommendation
from app.services.recommendation_engine import build_all_recommendations, build_recommendation

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=list[AssetRecommendation])
def get_all_recommendations(db: Session = Depends(get_db)) -> list[AssetRecommendation]:
    """Rekomendacje dla wszystkich aktywów posortowane: KUP → TRZYMAJ → SPRZEDAJ."""
    return build_all_recommendations(db)


@router.get("/assets/{asset_id}/recommendation", response_model=AssetRecommendation)
def get_asset_recommendation(asset_id: str, db: Session = Depends(get_db)) -> AssetRecommendation:
    """Szczegółowa rekomendacja dla jednego aktywa."""
    from fastapi import HTTPException
    result = build_recommendation(db, asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return result
