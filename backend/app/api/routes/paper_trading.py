from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.paper_trading import (
    MAX_ALLOCATION_BUCKETS,
    account_snapshot,
    allocate_recommended_amounts,
    get_or_create_account,
    journal,
    list_account_snapshots,
    place_market_order,
    set_strategy_active,
)

router = APIRouter(prefix="/paper", tags=["paper-trading"])


class AccountCreate(BaseModel):
    name: str = "default"
    initial_cash: float = Field(10000.0, gt=0)
    currency: str = Field("USD", min_length=3, max_length=8)


class OrderCreate(BaseModel):
    asset_id: str
    side: str
    quantity: float = Field(gt=0)
    commission_pct: float = Field(0.05, ge=0, le=5)
    slippage_pct: float = Field(0.05, ge=0, le=5)
    note: str = ""


class RecommendedAllocationCreate(BaseModel):
    amounts: list[float] = Field(min_length=1, max_length=MAX_ALLOCATION_BUCKETS)


class StrategyStatusUpdate(BaseModel):
    active: bool


@router.post("/accounts")
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    try:
        row = get_or_create_account(db, payload.name, payload.initial_cash, payload.currency)
        db.commit()
        return account_snapshot(db, row.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/accounts")
def list_accounts(currency: str | None = Query(None, min_length=3, max_length=8), db: Session = Depends(get_db)):
    return list_account_snapshots(db, currency)


@router.get("/accounts/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    try: return account_snapshot(db, account_id)
    except ValueError as exc: raise HTTPException(404, str(exc))


@router.post("/accounts/{account_id}/orders")
def order(account_id: int, payload: OrderCreate, db: Session = Depends(get_db)):
    try:
        row = place_market_order(db, account_id, payload.asset_id.lower(), payload.side.lower(),
                                 payload.quantity, payload.commission_pct, payload.slippage_pct, payload.note)
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}
    except ValueError as exc: raise HTTPException(422, str(exc))


@router.get("/accounts/{account_id}/journal")
def get_journal(account_id: int, limit: int = Query(200, ge=1, le=2000), db: Session = Depends(get_db)):
    return journal(db, account_id, limit)


@router.post("/accounts/{account_id}/recommended-allocations")
def recommended_allocations(
    account_id: int,
    payload: RecommendedAllocationCreate,
    db: Session = Depends(get_db),
):
    try:
        return allocate_recommended_amounts(db, account_id, payload.amounts)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/accounts/{account_id}/strategy/status")
def strategy_status(
    account_id: int,
    payload: StrategyStatusUpdate,
    db: Session = Depends(get_db),
):
    try:
        return set_strategy_active(db, account_id, payload.active)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
