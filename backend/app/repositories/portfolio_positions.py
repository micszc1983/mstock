from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import PortfolioPositionORM


def list_positions(db: Session) -> list[PortfolioPositionORM]:
    return db.query(PortfolioPositionORM).order_by(PortfolioPositionORM.asset_id).all()


def get_position(db: Session, asset_id: str) -> Optional[PortfolioPositionORM]:
    return db.query(PortfolioPositionORM).filter(PortfolioPositionORM.asset_id == asset_id).first()


def upsert_position(db: Session, asset_id: str, quantity: float, avg_buy_price: Optional[float] = None) -> PortfolioPositionORM:
    row = get_position(db, asset_id)
    if row is None:
        row = PortfolioPositionORM(asset_id=asset_id, quantity=quantity, avg_buy_price=avg_buy_price)
        db.add(row)
    else:
        row.quantity = quantity
        if avg_buy_price is not None:
            row.avg_buy_price = avg_buy_price
        row.updated_at = datetime.utcnow()
    return row


def delete_position(db: Session, asset_id: str) -> bool:
    row = get_position(db, asset_id)
    if row:
        db.delete(row)
        return True
    return False
