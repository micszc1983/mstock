from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import asset_to_schema, news_to_schema, price_to_schema
from app.repositories.assets import create_asset, delete_asset_cascade, get_asset, list_assets
from app.repositories.news import list_news, upsert_news_item
from app.repositories.prices import list_prices, upsert_price_point
from app.schemas.asset import Asset, AssetCreate, PricePoint
from app.schemas.news import IngestNewsRequest, NewsItem
from app.schemas.sync import IngestPriceRequest

router = APIRouter(prefix="/assets", tags=["assets"])


def _asset_or_404(db: Session, asset_id: str):
    asset = get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return asset


@router.get("", response_model=list[Asset])
def get_assets(db: Session = Depends(get_db)) -> list[Asset]:
    return [asset_to_schema(row) for row in list_assets(db)]


@router.get("/{asset_id}", response_model=Asset)
def get_asset_details(asset_id: str, db: Session = Depends(get_db)) -> Asset:
    return asset_to_schema(_asset_or_404(db, asset_id))



@router.post("", response_model=Asset, status_code=201)
def create_asset_endpoint(payload: AssetCreate, db: Session = Depends(get_db)) -> Asset:
    if get_asset(db, payload.id) is not None:
        raise HTTPException(status_code=409, detail=f"Asset '{payload.id}' already exists.")
    # Inferuj walutę jeśli nie podana: .WA → PLN, reszta → USD
    def _infer_currency(p: AssetCreate) -> str:
        if p.currency:
            return p.currency
        if (p.price_symbol or "").upper().endswith(".WA"):
            return "PLN"
        return "USD"

    row = create_asset(
        db,
        asset_id=payload.id.lower().strip(),
        symbol=payload.symbol.upper().strip(),
        name=payload.name,
        asset_type=payload.type.value,
        currency=_infer_currency(payload),
        sector=payload.sector,
        description=payload.description,
        price_symbol=payload.price_symbol or None,
        news_symbol=payload.news_symbol or None,
        news_term=payload.news_term or payload.name,
        metal_price_fn=payload.metal_price_fn or None,
    )
    db.commit()
    db.refresh(row)
    from app.mappers import asset_to_schema
    return asset_to_schema(row)


@router.delete("/{asset_id}", status_code=204)
def delete_asset_endpoint(asset_id: str, db: Session = Depends(get_db)) -> None:
    _asset_or_404(db, asset_id)
    delete_asset_cascade(db, asset_id)
    db.commit()


@router.patch("/{asset_id}", response_model=Asset)
def update_asset_provider_config(
    asset_id: str,
    payload: AssetCreate,
    db: Session = Depends(get_db),
) -> Asset:
    """Aktualizuje konfigurację providera dla istniejącego aktywa."""
    row = _asset_or_404(db, asset_id)
    row.price_symbol   = payload.price_symbol or None
    row.news_symbol    = payload.news_symbol or None
    row.news_term      = payload.news_term or row.name
    row.metal_price_fn = payload.metal_price_fn or None
    if payload.sector:
        row.sector = payload.sector
    if payload.description:
        row.description = payload.description
    db.commit()
    db.refresh(row)
    from app.mappers import asset_to_schema
    return asset_to_schema(row)

@router.get("/{asset_id}/prices", response_model=list[PricePoint])
def get_asset_prices(asset_id: str, limit: int = Query(default=5000, ge=5, le=5000), db: Session = Depends(get_db)) -> list[PricePoint]:
    _asset_or_404(db, asset_id)
    return [price_to_schema(row) for row in list_prices(db, asset_id, limit=limit)]


@router.post("/{asset_id}/prices", response_model=PricePoint)
def ingest_price(asset_id: str, payload: IngestPriceRequest, db: Session = Depends(get_db)) -> PricePoint:
    _asset_or_404(db, asset_id)
    point = PricePoint(**payload.model_dump())
    upsert_price_point(db, asset_id, point)
    db.commit()
    return point


@router.get("/{asset_id}/news", response_model=list[NewsItem])
def get_asset_news(asset_id: str, limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)) -> list[NewsItem]:
    _asset_or_404(db, asset_id)
    return [news_to_schema(row) for row in list_news(db, asset_id, limit=limit)]


@router.post("/{asset_id}/news", response_model=NewsItem)
def ingest_news(asset_id: str, payload: IngestNewsRequest, db: Session = Depends(get_db)) -> NewsItem:
    _asset_or_404(db, asset_id)
    item = NewsItem(asset_id=asset_id, **payload.model_dump())
    upsert_news_item(db, item)
    db.commit()
    return item
