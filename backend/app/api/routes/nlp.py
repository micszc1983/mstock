from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset, list_assets
from app.repositories.news import list_news
from app.schemas.nlp import NewsNLPResponse
from app.services.news_enrichment import enrich_news_for_asset, get_news_nlp_response

router = APIRouter(tags=["nlp"])


@router.post("/assets/{asset_id}/news/enrich")
def enrich_asset_news(asset_id: str, limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    enriched = enrich_news_for_asset(db, asset_id, limit=limit)
    return {"asset_id": asset_id, "enriched": enriched}


@router.post("/news/enrich/all")
def enrich_all_news(limit_per_asset: int = Query(default=200, ge=1, le=2000), db: Session = Depends(get_db)) -> dict:
    results = {}
    for asset in list_assets(db):
        n = enrich_news_for_asset(db, asset.id, limit=limit_per_asset)
        if n > 0:
            results[asset.id] = n
    return {"enriched": sum(results.values()), "per_asset": results}


@router.get("/news/{news_id}/nlp", response_model=NewsNLPResponse)
def get_news_nlp(news_id: str, db: Session = Depends(get_db)) -> NewsNLPResponse:
    response = get_news_nlp_response(db, news_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"No NLP result for news: {news_id}")
    return response
