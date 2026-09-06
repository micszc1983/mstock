from __future__ import annotations

import math
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (AssetORM, PaperAccountORM, PaperOrderORM, PaperPositionORM,
                           PaperStrategyBucketORM, PaperStrategyORM, PaperTradeORM,
                           PricePointORM, RecommendationRecordORM)
from app.services.market_calendar import is_market_open
from app.services.ohlcv_validation import validate_series
from app.utils.datetime import ensure_utc, now_utc


MAX_ALLOCATION_BUCKETS = 20


def _notify_filled_trade(
    order: PaperOrderORM,
    account: PaperAccountORM,
    asset: AssetORM,
    *,
    gross: float,
    realized: float,
) -> bool:
    """Send one best-effort SMS after a paper trade has been committed."""
    if settings.testing or not settings.sms_enabled:
        return False
    try:
        from app.services.sms_alert_config import get_section
        from app.services.sms_service import send_sms

        if not get_section("paper_trading_sms").get("enabled", True):
            return False
        side = "KUP" if order.side == "buy" else "SPRZEDAJ"
        symbol = (asset.symbol or asset.id).upper()
        costs = float(order.commission or 0) + float(order.slippage or 0)
        result = f"; wynik {realized:+.2f}" if order.side == "sell" else ""
        message = (
            f"MStock PAPER {side} {symbol}: {order.quantity:g} szt po "
            f"{float(order.fill_price or 0):.2f} {account.currency}; "
            f"wartosc {gross:.2f}; koszty {costs:.2f}{result}; "
            f"konto {account.name[:24]}; ID {order.id}"
        )
        return send_sms(message)
    except Exception as exc:
        # Powiadomienie nie może cofnąć ani oznaczyć jako nieudaną już
        # zaksięgowaną transakcję paper tradingu.
        print(f"[paper-trading] Błąd SMS dla zlecenia #{order.id}: {exc}")
        return False


def _validated_reference_price(db: Session, asset_id: str) -> float:
    recent = db.scalars(
        select(PricePointORM)
        .where(PricePointORM.asset_id == asset_id)
        .order_by(PricePointORM.timestamp.desc())
        .limit(100)
    ).all()[::-1]
    quality = validate_series(recent)
    if not recent or not quality["valid"]:
        raise ValueError("Order blocked: missing or invalid OHLCV data")
    reference = float(recent[-1].close)
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("Order blocked: invalid reference price")
    return reference


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
            "unrealized_pnl": round(unrealized, 2), "positions": rows,
            "strategy": strategy_snapshot(db, account_id)}


def list_account_snapshots(db: Session, currency: str | None = None) -> list[dict]:
    stmt = select(PaperAccountORM).order_by(PaperAccountORM.updated_at.desc())
    if currency:
        stmt = stmt.where(PaperAccountORM.currency == currency.upper())
    return [account_snapshot(db, account.id) for account in db.scalars(stmt).all()]


def strategy_snapshot(db: Session, account_id: int) -> dict | None:
    strategy = db.scalar(
        select(PaperStrategyORM).where(PaperStrategyORM.account_id == account_id)
    )
    if not strategy:
        return None
    buckets = db.scalars(
        select(PaperStrategyBucketORM)
        .where(PaperStrategyBucketORM.strategy_id == strategy.id)
        .order_by(PaperStrategyBucketORM.ordinal.asc())
    ).all()
    rows = []
    for bucket in buckets:
        last_price = None
        asset_value = 0.0
        displayed_action = None
        if bucket.asset_id and bucket.quantity > 0:
            latest = db.scalar(
                select(PricePointORM)
                .where(PricePointORM.asset_id == bucket.asset_id)
                .order_by(PricePointORM.timestamp.desc())
                .limit(1)
            )
            last_price = float(latest.close) if latest else bucket.avg_price
            asset_value = bucket.quantity * last_price
            latest_signal = db.scalar(
                select(RecommendationRecordORM)
                .where(RecommendationRecordORM.asset_id == bucket.asset_id)
                .order_by(
                    RecommendationRecordORM.created_at.desc(),
                    RecommendationRecordORM.revision.desc(),
                )
                .limit(1)
            )
            displayed_action = latest_signal.displayed_action if latest_signal else None
        if bucket.asset_id and bucket.quantity > 0:
            if displayed_action == "SPRZEDAJ":
                signal_status = "exit_signal"
                signal_message = "Aktywny sygnał SPRZEDAJ — zamknięcie w następnym cyklu"
            elif displayed_action == "KUP":
                signal_status = "entry_active"
                signal_message = "Sygnał wejścia nadal aktywny"
            else:
                signal_status = "entry_expired"
                signal_message = "Sygnał wejścia wygasł — pozycja jest utrzymywana do jawnego SPRZEDAJ"
        elif bucket.pending_asset_id:
            signal_status = "confirming"
            signal_message = (
                f"Potwierdzanie KUP: {bucket.pending_signal_count}/"
                f"{max(1, settings.paper_entry_confirmation_cycles)}"
            )
        else:
            signal_status = "waiting"
            signal_message = "Oczekuje na potwierdzoną rekomendację KUP"
        rows.append({
            "id": bucket.id,
            "ordinal": bucket.ordinal,
            "initial_amount": round(bucket.initial_amount, 2),
            "cash": round(bucket.cash, 2),
            "asset_id": bucket.asset_id,
            "quantity": bucket.quantity,
            "avg_price": bucket.avg_price,
            "last_price": last_price,
            "value": round(bucket.cash + asset_value, 2),
            "return_pct": round(
                ((bucket.cash + asset_value) / bucket.initial_amount - 1) * 100, 3
            ) if bucket.initial_amount else 0.0,
            "status": "position" if bucket.asset_id and bucket.quantity > 0 else "waiting",
            "signal_status": signal_status,
            "signal_message": signal_message,
            "current_recommendation": displayed_action,
            "pending_asset_id": bucket.pending_asset_id,
            "pending_signal_count": bucket.pending_signal_count,
            "pending_since": bucket.pending_since,
            "opened_at": bucket.opened_at,
            "updated_at": bucket.updated_at,
        })
    return {
        "id": strategy.id,
        "active": strategy.active,
        "created_at": strategy.created_at,
        "updated_at": strategy.updated_at,
        "last_run_at": strategy.last_run_at,
        "last_message": strategy.last_message,
        "buckets": rows,
    }


def place_market_order(db: Session, account_id: int, asset_id: str, side: str, quantity: float,
                       commission_pct: float = 0.05, slippage_pct: float = 0.05, note: str = "") -> PaperOrderORM:
    if side not in {"buy", "sell"} or quantity <= 0:
        raise ValueError("side must be buy/sell and quantity must be positive")
    account = db.get(PaperAccountORM, account_id)
    asset = db.get(AssetORM, asset_id)
    if not account or not asset:
        raise ValueError("Unknown account or asset")
    if account.currency.upper() != asset.currency.upper():
        raise ValueError(
            f"Currency mismatch: account uses {account.currency}, asset uses {asset.currency}"
        )
    reference = _validated_reference_price(db, asset_id)
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
    _notify_filled_trade(order, account, asset, gross=gross, realized=realized)
    return order


def allocate_recommended_amounts(
    db: Session,
    account_id: int,
    amounts: list[float],
) -> dict:
    """Persist and start an automatic strategy for user-provided cash buckets."""
    account = db.get(PaperAccountORM, account_id)
    if not account:
        raise ValueError("Unknown paper account")
    if not amounts or len(amounts) > MAX_ALLOCATION_BUCKETS:
        raise ValueError(f"Provide between 1 and {MAX_ALLOCATION_BUCKETS} amounts")

    budgets: list[float] = []
    for amount in amounts:
        value = float(amount)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Every investment amount must be positive and finite")
        budgets.append(round(value, 2))
    if sum(budgets) > account.cash + 1e-6:
        raise ValueError(
            f"Insufficient cash: requested {sum(budgets):.2f} {account.currency}, "
            f"available {account.cash:.2f} {account.currency}"
        )

    existing = db.scalar(
        select(PaperStrategyORM).where(PaperStrategyORM.account_id == account.id)
    )
    if existing:
        raise ValueError(
            "Automatic paper strategy already exists for this account; "
            "reuse or pause it instead of creating a second one"
        )

    now = now_utc()
    strategy = PaperStrategyORM(
        account_id=account.id,
        active=True,
        created_at=now,
        updated_at=now,
        last_run_at=None,
        last_message="Strategia utworzona — oczekuje na pierwszą decyzję",
    )
    db.add(strategy)
    db.flush()
    for ordinal, budget in enumerate(budgets, start=1):
        db.add(PaperStrategyBucketORM(
            strategy_id=strategy.id,
            ordinal=ordinal,
            initial_amount=budget,
            cash=budget,
            asset_id=None,
            pending_asset_id=None,
            pending_signal_count=0,
            pending_since=None,
            quantity=0.0,
            avg_price=0.0,
            opened_at=None,
            updated_at=now,
        ))
    db.commit()

    from app.services.recommendation_engine import build_all_recommendations
    result = run_paper_strategy(db, strategy, build_all_recommendations(db))
    snapshot = strategy_snapshot(db, account.id)
    unallocated = [
        {
            "amount": bucket["cash"],
            "reason": "Oczekuje na odpowiednie aktywo z rekomendacją KUP",
        }
        for bucket in (snapshot or {}).get("buckets", [])
        if bucket["status"] == "waiting"
    ]

    return {
        "requested_amounts": budgets,
        "allocations": result["buys"],
        "unallocated": unallocated,
        "account": account_snapshot(db, account.id),
    }


def _ranked_buy_recommendations(db: Session, recommendations: list, currency: str) -> list:
    ranked = [
        rec for rec in recommendations
        if rec.recommendation == "KUP"
        and rec.data_complete
        and not rec.has_critical_alert
        and rec.expected_net_edge_pct > 0
    ]
    ranked.sort(
        key=lambda rec: (
            rec.confidence,
            rec.expected_net_edge_pct - rec.uncertainty_pct,
            rec.composite_score,
        ),
        reverse=True,
    )
    eligible = []
    for rec in ranked:
        asset = db.get(AssetORM, rec.asset_id)
        if not asset or asset.currency.upper() != currency.upper():
            continue
        try:
            reference = _validated_reference_price(db, asset.id)
        except ValueError:
            continue
        eligible.append((rec, reference))
    return eligible


def _entry_session_ready(asset: AssetORM, recommendation, at) -> tuple[bool, str | None]:
    """Allow a daily strategy entry only after today's market candle is closed."""
    if not settings.paper_require_closed_session_entry or asset.type != "stock":
        return True, None
    symbol = asset.price_symbol or asset.symbol or ""
    if is_market_open(symbol, at):
        return False, "sesja nadal trwa"
    snapshot_at = ensure_utc(getattr(recommendation, "snapshot_at", None))
    if snapshot_at is None:
        return False, "rekomendacja nie ma czasu zamkniętej świecy"
    market = getattr(recommendation, "market_segment", None)
    zone = ZoneInfo("Europe/Warsaw" if market == "GPW" or symbol.upper().endswith(".WA") else "America/New_York")
    local_now = ensure_utc(at).astimezone(zone)
    if snapshot_at.astimezone(zone).date() != local_now.date():
        return False, "brak zamkniętej świecy z bieżącej sesji"
    return True, None


def _clear_pending_entry(bucket: PaperStrategyBucketORM) -> None:
    bucket.pending_asset_id = None
    bucket.pending_signal_count = 0
    bucket.pending_since = None


def run_paper_strategy(db: Session, strategy: PaperStrategyORM, recommendations: list) -> dict:
    """Execute one background strategy using the latest frozen recommendations."""
    account = db.get(PaperAccountORM, strategy.account_id)
    if not account:
        raise ValueError("Unknown paper account")
    buckets = db.scalars(
        select(PaperStrategyBucketORM)
        .where(PaperStrategyBucketORM.strategy_id == strategy.id)
        .order_by(PaperStrategyBucketORM.ordinal.asc())
    ).all()
    rec_by_asset = {rec.asset_id: rec for rec in recommendations}
    now = now_utc()
    buys: list[dict] = []
    sells: list[dict] = []

    # Exit first.  A neutral/no-trade recommendation keeps an existing paper
    # position; only an explicit calibrated SELL closes it.
    for bucket in buckets:
        if not bucket.asset_id or bucket.quantity <= 0:
            continue
        rec = rec_by_asset.get(bucket.asset_id)
        if not rec or rec.recommendation != "SPRZEDAJ":
            continue
        position = db.scalar(
            select(PaperPositionORM).where(
                PaperPositionORM.account_id == account.id,
                PaperPositionORM.asset_id == bucket.asset_id,
            )
        )
        if not position or position.quantity <= 0:
            bucket.asset_id = None
            _clear_pending_entry(bucket)
            bucket.quantity = 0.0
            bucket.avg_price = 0.0
            bucket.opened_at = None
            bucket.updated_at = now
            continue
        quantity = min(bucket.quantity, position.quantity)
        component_pct = max(float(rec.transaction_cost_pct), 0.0) / 4.0
        order = place_market_order(
            db, account.id, bucket.asset_id, "sell", quantity,
            commission_pct=component_pct,
            slippage_pct=component_pct,
            note=(
                "Automatyczne zamknięcie koszyka po rekomendacji SPRZEDAJ; "
                f"confidence={rec.confidence:.1f}%; przewaga_netto={rec.expected_net_edge_pct:.3f}%"
            ),
        )
        if order.status != "filled":
            continue
        proceeds = float(order.fill_price or 0) * quantity - float(order.commission)
        old_asset_id = bucket.asset_id
        bucket.cash += proceeds
        bucket.asset_id = None
        _clear_pending_entry(bucket)
        bucket.quantity = 0.0
        bucket.avg_price = 0.0
        bucket.opened_at = None
        bucket.updated_at = now
        sells.append({
            "amount": round(proceeds, 2),
            "asset_id": old_asset_id,
            "quantity": quantity,
            "fill_price": round(float(order.fill_price or 0), 6),
            "order_id": order.id,
        })

    occupied = {bucket.asset_id for bucket in buckets if bucket.asset_id}
    candidates = _ranked_buy_recommendations(db, recommendations, account.currency)
    candidate_index = 0
    confirming = 0
    session_blocked = 0
    required_confirmations = max(1, settings.paper_entry_confirmation_cycles)
    for bucket in buckets:
        if bucket.asset_id or bucket.cash <= 0:
            continue
        while candidate_index < len(candidates) and candidates[candidate_index][0].asset_id in occupied:
            candidate_index += 1
        if candidate_index >= len(candidates):
            if bucket.pending_asset_id:
                _clear_pending_entry(bucket)
                bucket.updated_at = now
            continue
        rec, reference = candidates[candidate_index]
        candidate_index += 1
        occupied.add(rec.asset_id)
        asset = db.get(AssetORM, rec.asset_id)
        if asset is None:
            _clear_pending_entry(bucket)
            continue
        session_ready, _ = _entry_session_ready(asset, rec, now)
        if not session_ready:
            if bucket.pending_asset_id != rec.asset_id:
                bucket.pending_asset_id = rec.asset_id
                bucket.pending_since = now
            bucket.pending_signal_count = 0
            bucket.updated_at = now
            session_blocked += 1
            continue
        if bucket.pending_asset_id == rec.asset_id:
            bucket.pending_signal_count += 1
        else:
            bucket.pending_asset_id = rec.asset_id
            bucket.pending_signal_count = 1
            bucket.pending_since = now
        bucket.updated_at = now
        if bucket.pending_signal_count < required_confirmations:
            confirming += 1
            continue
        component_pct = max(float(rec.transaction_cost_pct), 0.0) / 4.0
        fill_price = reference * (1 + component_pct / 100)
        unit_cash_cost = fill_price * (1 + component_pct / 100)
        quantity = math.floor((bucket.cash / unit_cash_cost) * 100_000_000) / 100_000_000
        if quantity <= 0:
            continue
        order = place_market_order(
            db, account.id, rec.asset_id, "buy", quantity,
            commission_pct=component_pct,
            slippage_pct=component_pct,
            note=(
                f"Automatyczny koszyk {bucket.ordinal}; budżet={bucket.cash:.2f} {account.currency}; "
                f"rekomendacja=KUP; confidence={rec.confidence:.1f}%; "
                f"przewaga_netto={rec.expected_net_edge_pct:.3f}%; "
                f"niepewność={rec.uncertainty_pct:.3f}%; rynek={rec.market_segment}; reżim={rec.regime}"
            ),
        )
        if order.status != "filled":
            continue
        invested = float(order.fill_price or 0) * quantity + float(order.commission)
        bucket.cash = max(0.0, bucket.cash - invested)
        bucket.asset_id = rec.asset_id
        _clear_pending_entry(bucket)
        bucket.quantity = quantity
        bucket.avg_price = invested / quantity
        bucket.opened_at = now
        bucket.updated_at = now
        buys.append({
            "amount": round(invested + bucket.cash, 2),
            "asset_id": rec.asset_id,
            "symbol": rec.symbol,
            "name": rec.name,
            "quantity": quantity,
            "reference_price": round(reference, 6),
            "fill_price": round(float(order.fill_price or 0), 6),
            "invested_amount": round(invested, 2),
            "entry_costs": round(float(order.commission) + float(order.slippage), 2),
            "confidence": rec.confidence,
            "expected_net_edge_pct": rec.expected_net_edge_pct,
            "uncertainty_pct": rec.uncertainty_pct,
            "market_segment": rec.market_segment,
            "regime": rec.regime,
            "order_id": order.id,
        })

    waiting = sum(1 for bucket in buckets if not bucket.asset_id)
    strategy.last_run_at = now
    strategy.updated_at = now
    strategy.last_message = (
        f"Cykl zakończony: kupiono {len(buys)}, sprzedano {len(sells)}, "
        f"pozycje {len(buckets) - waiting}, oczekujące koszyki {waiting}, "
        f"potwierdzane sygnały {confirming}, oczekujące na zamknięcie sesji {session_blocked}"
    )
    db.commit()
    return {
        "strategy_id": strategy.id,
        "buys": buys,
        "sells": sells,
        "waiting": waiting,
        "confirming": confirming,
        "session_blocked": session_blocked,
    }


def run_active_paper_strategies(db: Session) -> list[dict]:
    strategies = db.scalars(
        select(PaperStrategyORM).where(PaperStrategyORM.active.is_(True))
    ).all()
    if not strategies:
        return []
    from app.services.recommendation_engine import build_all_recommendations
    recommendations = build_all_recommendations(db)
    results = []
    for strategy in strategies:
        try:
            results.append(run_paper_strategy(db, strategy, recommendations))
        except Exception as exc:
            db.rollback()
            current = db.get(PaperStrategyORM, strategy.id)
            if current:
                current.last_run_at = now_utc()
                current.updated_at = now_utc()
                current.last_message = f"Błąd cyklu: {str(exc)[:300]}"
                db.commit()
            results.append({"strategy_id": strategy.id, "error": str(exc)})
    return results


def set_strategy_active(db: Session, account_id: int, active: bool) -> dict:
    strategy = db.scalar(
        select(PaperStrategyORM).where(PaperStrategyORM.account_id == account_id)
    )
    if not strategy:
        raise ValueError("Paper strategy does not exist")
    strategy.active = active
    strategy.updated_at = now_utc()
    strategy.last_message = "Strategia wznowiona" if active else "Strategia wstrzymana przez użytkownika"
    db.commit()
    return strategy_snapshot(db, account_id) or {}


def journal(db: Session, account_id: int, limit: int = 200) -> dict:
    orders = db.scalars(select(PaperOrderORM).where(PaperOrderORM.account_id == account_id)
                        .order_by(PaperOrderORM.submitted_at.desc()).limit(limit)).all()
    trades = db.scalars(select(PaperTradeORM).where(PaperTradeORM.account_id == account_id)
                        .order_by(PaperTradeORM.executed_at.desc()).limit(limit)).all()
    def row(obj):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return {"orders": [row(x) for x in orders], "trades": [row(x) for x in trades]}
