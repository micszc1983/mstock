from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (AssetORM, PaperAccountORM, PaperOrderORM, PaperPositionORM,
                           PaperTradeORM, PricePointORM)
from app.services.ohlcv_validation import validate_series
from app.utils.datetime import now_utc


def get_or_create_account(
    db: Session,
    name: str = "default",
    initial_cash: float = 10000.0,
    currency: str = "USD",
) -> PaperAccountORM:
    account = db.scalar(select(PaperAccountORM).where(PaperAccountORM.name == name))
    if account:
        if account.currency != currency.upper():
            raise ValueError(f"Account {name} uses {account.currency}, not {currency.upper()}")
        return account
    now = now_utc()
    account = PaperAccountORM(name=name, currency=currency.upper(), initial_cash=initial_cash, cash=initial_cash,
                              created_at=now, updated_at=now)
    db.add(account); db.flush()
    return account


def account_snapshot(db: Session, account_id: int) -> dict:
    account = db.get(PaperAccountORM, account_id)
    if not account:
        raise ValueError("Unknown paper account")
    positions = db.scalars(select(PaperPositionORM).where(PaperPositionORM.account_id == account_id)).all()
    rows, market_value, unrealized = [], 0.0, 0.0
    for position in positions:
        latest = db.scalar(select(PricePointORM).where(PricePointORM.asset_id == position.asset_id)
                           .order_by(PricePointORM.timestamp.desc()).limit(1))
        price = latest.close if latest else position.avg_price
        value = position.quantity * price
        upnl = (price - position.avg_price) * position.quantity
        market_value += value; unrealized += upnl
        rows.append({"asset_id": position.asset_id, "quantity": position.quantity,
                     "avg_price": position.avg_price, "last_price": price,
                     "market_value": round(value, 2), "unrealized_pnl": round(upnl, 2),
                     "realized_pnl": round(position.realized_pnl, 2)})
    equity = account.cash + market_value
    return {"id": account.id, "name": account.name, "currency": account.currency,
            "initial_cash": account.initial_cash, "cash": round(account.cash, 2),
            "market_value": round(market_value, 2), "equity": round(equity, 2),
            "total_return_pct": round((equity / account.initial_cash - 1) * 100, 3),
            "unrealized_pnl": round(unrealized, 2), "positions": rows}


def place_market_order(db: Session, account_id: int, asset_id: str, side: str, quantity: float,
                       commission_pct: float = 0.05, slippage_pct: float = 0.05, note: str = "") -> PaperOrderORM:
    if side not in {"buy", "sell"} or quantity <= 0:
        raise ValueError("side must be buy/sell and quantity must be positive")
    account = db.get(PaperAccountORM, account_id)
    asset = db.get(AssetORM, asset_id)
    if not account or not asset:
        raise ValueError("Unknown account or asset")
    if account.currency != asset.currency:
        raise ValueError(
            f"Currency mismatch: account uses {account.currency}, asset uses {asset.currency}"
        )
    recent = db.scalars(select(PricePointORM).where(PricePointORM.asset_id == asset_id)
                        .order_by(PricePointORM.timestamp.desc()).limit(100)).all()[::-1]
    quality = validate_series(recent)
    if not recent or not quality["valid"]:
        raise ValueError("Order blocked: missing or invalid OHLCV data")
    reference = recent[-1].close
    fill = reference * (1 + slippage_pct / 100 if side == "buy" else 1 - slippage_pct / 100)
    gross = fill * quantity
    commission = gross * commission_pct / 100
    now = now_utc()
    order = PaperOrderORM(account_id=account_id, asset_id=asset_id, side=side, order_type="market",
        quantity=quantity, status="submitted", submitted_at=now, reference_price=reference,
        fill_price=None, commission=0.0, slippage=0.0, note=note)
    db.add(order); db.flush()
    position = db.scalar(select(PaperPositionORM).where(PaperPositionORM.account_id == account_id,
                                                        PaperPositionORM.asset_id == asset_id))
    realized = 0.0
    if side == "buy":
        if gross + commission > account.cash:
            order.status = "rejected"; order.note = "Insufficient cash"; db.commit(); return order
        old_qty = position.quantity if position else 0.0
        old_cost = old_qty * position.avg_price if position else 0.0
        if not position:
            position = PaperPositionORM(account_id=account_id, asset_id=asset_id, quantity=0,
                                        avg_price=0, realized_pnl=0, updated_at=now); db.add(position)
        position.quantity = old_qty + quantity
        position.avg_price = (old_cost + gross + commission) / position.quantity
        account.cash -= gross + commission
    else:
        if not position or position.quantity + 1e-9 < quantity:
            order.status = "rejected"; order.note = "Insufficient position"; db.commit(); return order
        realized = (fill - position.avg_price) * quantity - commission
        position.quantity -= quantity; position.realized_pnl += realized
        account.cash += gross - commission
        if position.quantity <= 1e-9:
            db.delete(position)
    order.status = "filled"; order.filled_at = now; order.fill_price = fill
    order.commission = commission; order.slippage = abs(fill - reference) * quantity
    account.updated_at = now
    db.add(PaperTradeORM(order_id=order.id, account_id=account_id, asset_id=asset_id, side=side,
        quantity=quantity, price=fill, gross_value=gross, costs=commission + order.slippage,
        realized_pnl=realized, executed_at=now))
    db.commit(); db.refresh(order)
    return order


def journal(db: Session, account_id: int, limit: int = 200) -> dict:
    orders = db.scalars(select(PaperOrderORM).where(PaperOrderORM.account_id == account_id)
                        .order_by(PaperOrderORM.submitted_at.desc()).limit(limit)).all()
    trades = db.scalars(select(PaperTradeORM).where(PaperTradeORM.account_id == account_id)
                        .order_by(PaperTradeORM.executed_at.desc()).limit(limit)).all()
    def row(obj):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return {"orders": [row(x) for x in orders], "trades": [row(x) for x in trades]}
