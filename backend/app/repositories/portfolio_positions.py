from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import PortfolioPositionORM


def list_positions(db: Session) -> list[PortfolioPositionORM]:
    return db.query(PortfolioPositionORM).order_by(PortfolioPositionORM.asset_id).all()


def get_position(db: Session, asset_id: str) -> Optional[PortfolioPositionORM]:
    return db.query(PortfolioPositionORM).filter(PortfolioPositionORM.asset_id == asset_id).first()


def upsert_position(
    db: Session,
    asset_id: str,
    quantity: float,
    avg_buy_price: Optional[float] = None,
    *,
    purchase_date: Optional[date] = None,
    invested_amount: Optional[float] = None,
) -> PortfolioPositionORM:
    row = get_position(db, asset_id)
    if row is None:
        row = PortfolioPositionORM(
            asset_id=asset_id,
            quantity=quantity,
            avg_buy_price=avg_buy_price,
            purchase_date=purchase_date,
            invested_amount=(
                invested_amount
                if invested_amount is not None
                else quantity * avg_buy_price if avg_buy_price is not None else None
            ),
            cost_currency="PLN",
        )
        db.add(row)
    else:
        row.quantity = quantity
        if avg_buy_price is not None:
            row.avg_buy_price = avg_buy_price
            row.cost_currency = "PLN"
        if purchase_date is not None:
            row.purchase_date = purchase_date
        if invested_amount is not None:
            row.invested_amount = invested_amount
        elif row.avg_buy_price is not None:
            # Ręczna korekta liczby sztuk nie może pozostawić starej,
            # niespójnej wartości zainwestowanego kapitału.
            row.invested_amount = quantity * row.avg_buy_price
        row.updated_at = datetime.now(timezone.utc)
    return row


def add_purchase_to_position(
    db: Session,
    asset_id: str,
    quantity: float,
    purchase_price: float,
    purchase_date: date,
    invested_amount: float,
) -> PortfolioPositionORM:
    """Add a lot and maintain a consistent weighted-average position."""
    row = get_position(db, asset_id)
    if row is None:
        row = PortfolioPositionORM(
            asset_id=asset_id,
            quantity=quantity,
            avg_buy_price=purchase_price,
            purchase_date=purchase_date,
            invested_amount=invested_amount,
            cost_currency="PLN",
        )
        db.add(row)
        return row

    previous_invested = row.invested_amount
    if previous_invested is None and row.avg_buy_price is not None:
        previous_invested = row.quantity * row.avg_buy_price
    if previous_invested is None:
        raise ValueError(
            "Istniejąca pozycja nie ma ceny zakupu. Uzupełnij ją w edycji przed dokupieniem."
        )
    total_quantity = row.quantity + quantity
    total_invested = previous_invested + invested_amount
    row.quantity = total_quantity
    row.invested_amount = total_invested
    row.avg_buy_price = total_invested / total_quantity
    row.cost_currency = "PLN"
    row.purchase_date = min(row.purchase_date, purchase_date) if row.purchase_date else purchase_date
    row.updated_at = datetime.now(timezone.utc)
    return row


def update_position(
    db: Session,
    asset_id: str,
    *,
    new_asset_id: str,
    quantity: float,
    avg_buy_price: Optional[float],
    purchase_date: Optional[date],
) -> PortfolioPositionORM | None:
    row = get_position(db, asset_id)
    if row is None:
        return None
    row.asset_id = new_asset_id
    row.quantity = quantity
    row.avg_buy_price = avg_buy_price
    row.purchase_date = purchase_date
    row.invested_amount = quantity * avg_buy_price if avg_buy_price is not None else None
    row.cost_currency = "PLN"
    row.updated_at = datetime.now(timezone.utc)
    return row


def delete_position(db: Session, asset_id: str) -> bool:
    row = get_position(db, asset_id)
    if row:
        db.delete(row)
        return True
    return False
