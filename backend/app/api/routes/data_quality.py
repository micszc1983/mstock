from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset
from app.schemas.data_quality import AssetDataQuality, DataQualityReport
from app.services.data_quality import check_all_quality, check_asset_quality

router = APIRouter(tags=["data-quality"])


@router.get("/data-quality", response_model=DataQualityReport)
def get_data_quality(db: Session = Depends(get_db)) -> DataQualityReport:
    """Pełny raport jakości danych dla wszystkich aktywów."""
    return check_all_quality(db)


@router.get("/assets/{asset_id}/data-quality", response_model=AssetDataQuality)
def get_asset_data_quality(asset_id: str, db: Session = Depends(get_db)) -> AssetDataQuality:
    """Raport jakości danych dla jednego aktywa."""
    from fastapi import HTTPException
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return check_asset_quality(db, asset_row)
