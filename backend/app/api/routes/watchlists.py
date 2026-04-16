from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.assets import get_asset
from app.repositories.watchlists import (
    add_asset_to_watchlist,
    create_watchlist,
    get_watchlist,
    list_preferences,
    list_watchlist_assets,
    list_watchlists,
    delete_watchlist,
    remove_asset_from_watchlist,
    upsert_preference,
)
from app.schemas.watchlists import PreferenceResponse, PreferenceUpsert, WatchlistCreate, WatchlistResponse

router = APIRouter(tags=["watchlists"])


@router.post("/watchlists", response_model=WatchlistResponse)
def create_watchlist_endpoint(payload: WatchlistCreate, db: Session = Depends(get_db)) -> WatchlistResponse:
    row = create_watchlist(db, payload.name, payload.description, payload.is_default)
    db.commit()
    db.refresh(row)
    return WatchlistResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        is_default=row.is_default,
        created_at=row.created_at,
        assets=[],
    )


@router.get("/watchlists", response_model=list[WatchlistResponse])
def get_watchlists(db: Session = Depends(get_db)) -> list[WatchlistResponse]:
    rows = list_watchlists(db)
    return [
        WatchlistResponse(
            id=row.id,
            name=row.name,
            description=row.description,
            is_default=row.is_default,
            created_at=row.created_at,
            assets=list_watchlist_assets(db, row.id),
        )
        for row in rows
    ]


@router.post("/watchlists/{watchlist_id}/assets/{asset_id}", response_model=WatchlistResponse)
def add_asset(watchlist_id: int, asset_id: str, db: Session = Depends(get_db)) -> WatchlistResponse:
    watchlist = get_watchlist(db, watchlist_id)
    if watchlist is None:
        raise HTTPException(status_code=404, detail="Unknown watchlist")
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail="Unknown asset")
    add_asset_to_watchlist(db, watchlist_id, asset_id)
    db.commit()
    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        description=watchlist.description,
        is_default=watchlist.is_default,
        created_at=watchlist.created_at,
        assets=list_watchlist_assets(db, watchlist.id),
    )


@router.delete("/watchlists/{watchlist_id}/assets/{asset_id}", response_model=WatchlistResponse)
def remove_asset(watchlist_id: int, asset_id: str, db: Session = Depends(get_db)) -> WatchlistResponse:
    watchlist = get_watchlist(db, watchlist_id)
    if watchlist is None:
        raise HTTPException(status_code=404, detail="Unknown watchlist")
    remove_asset_from_watchlist(db, watchlist_id, asset_id)
    db.commit()
    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        description=watchlist.description,
        is_default=watchlist.is_default,
        created_at=watchlist.created_at,
        assets=list_watchlist_assets(db, watchlist.id),
    )


@router.delete("/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist_endpoint(watchlist_id: int, db: Session = Depends(get_db)) -> None:
    if get_watchlist(db, watchlist_id) is None:
        raise HTTPException(status_code=404, detail="Unknown watchlist")
    delete_watchlist(db, watchlist_id)
    db.commit()


@router.post("/preferences", response_model=PreferenceResponse)
def upsert_preference_endpoint(payload: PreferenceUpsert, db: Session = Depends(get_db)) -> PreferenceResponse:
    row = upsert_preference(db, payload.preference_key, payload.preference_value)
    db.commit()
    db.refresh(row)
    return PreferenceResponse(
        id=row.id,
        preference_key=row.preference_key,
        preference_value=row.preference_value,
        updated_at=row.updated_at,
    )


@router.get("/preferences", response_model=list[PreferenceResponse])
def get_preferences(db: Session = Depends(get_db)) -> list[PreferenceResponse]:
    return [
        PreferenceResponse(
            id=row.id,
            preference_key=row.preference_key,
            preference_value=row.preference_value,
            updated_at=row.updated_at,
        )
        for row in list_preferences(db)
    ]
