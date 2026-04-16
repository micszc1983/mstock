from __future__ import annotations

from app.utils.datetime import now_utc

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import UserPreferenceORM, WatchlistItemORM, WatchlistORM


def create_watchlist(db: Session, name: str, description: str | None, is_default: bool) -> WatchlistORM:
    row = WatchlistORM(
        name=name,
        description=description,
        is_default=is_default,
        created_at=now_utc(),
    )
    db.add(row)
    db.flush()
    return row


def list_watchlists(db: Session) -> list[WatchlistORM]:
    return db.scalars(select(WatchlistORM).order_by(WatchlistORM.created_at.desc())).all()


def get_watchlist(db: Session, watchlist_id: int) -> WatchlistORM | None:
    return db.get(WatchlistORM, watchlist_id)


def add_asset_to_watchlist(db: Session, watchlist_id: int, asset_id: str) -> WatchlistItemORM:
    existing = db.scalar(
        select(WatchlistItemORM).where(
            WatchlistItemORM.watchlist_id == watchlist_id,
            WatchlistItemORM.asset_id == asset_id,
        )
    )
    if existing:
        return existing
    row = WatchlistItemORM(
        watchlist_id=watchlist_id,
        asset_id=asset_id,
        created_at=now_utc(),
    )
    db.add(row)
    db.flush()
    return row


def remove_asset_from_watchlist(db: Session, watchlist_id: int, asset_id: str) -> None:
    db.execute(
        delete(WatchlistItemORM).where(
            WatchlistItemORM.watchlist_id == watchlist_id,
            WatchlistItemORM.asset_id == asset_id,
        )
    )


def list_watchlist_assets(db: Session, watchlist_id: int) -> list[str]:
    rows = db.scalars(
        select(WatchlistItemORM).where(WatchlistItemORM.watchlist_id == watchlist_id).order_by(WatchlistItemORM.created_at.asc())
    ).all()
    return [row.asset_id for row in rows]


def upsert_preference(db: Session, preference_key: str, preference_value: str) -> UserPreferenceORM:
    row = db.scalar(select(UserPreferenceORM).where(UserPreferenceORM.preference_key == preference_key))
    if row:
        row.preference_value = preference_value
        row.updated_at = now_utc()
        return row
    row = UserPreferenceORM(
        preference_key=preference_key,
        preference_value=preference_value,
        updated_at=now_utc(),
    )
    db.add(row)
    db.flush()
    return row


def list_preferences(db: Session) -> list[UserPreferenceORM]:
    return db.scalars(select(UserPreferenceORM).order_by(UserPreferenceORM.preference_key.asc())).all()


def delete_watchlist(db: Session, watchlist_id: int) -> None:
    db.execute(delete(WatchlistItemORM).where(WatchlistItemORM.watchlist_id == watchlist_id))
    row = db.get(WatchlistORM, watchlist_id)
    if row:
        db.delete(row)
