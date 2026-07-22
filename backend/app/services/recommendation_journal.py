"""Trwały dziennik rekomendacji i ocena ich wyników po sesjach 1/5/20."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PricePointORM, RecommendationRecordORM
from app.schemas.recommendation import AssetRecommendation


MODEL_VERSION = "calibrated_v6_oof_meta"
HORIZONS = (1, 5, 20)


def _model_action(recommendation: str) -> str:
    if recommendation == "KUP":
        return "BUY"
    if recommendation == "SPRZEDAJ":
        return "SELL"
    return "NO_TRADE"


def persist_recommendation(
    db: Session,
    rec: AssetRecommendation,
    *,
    has_position: bool = False,
) -> RecommendationRecordORM | None:
    """Zapisuje snapshot idempotentnie; endpointy GET nie modyfikują historii."""
    if rec.snapshot_at is None:
        return None
    existing = db.scalar(
        select(RecommendationRecordORM).where(
            RecommendationRecordORM.asset_id == rec.asset_id,
            RecommendationRecordORM.snapshot_at == rec.snapshot_at,
            RecommendationRecordORM.model_version == MODEL_VERSION,
        )
    )
    if existing is not None:
        return existing
    row = RecommendationRecordORM(
        asset_id=rec.asset_id,
        snapshot_at=rec.snapshot_at,
        created_at=datetime.now(timezone.utc),
        model_version=MODEL_VERSION,
        market=rec.market_segment,
        regime=rec.regime,
        action=_model_action(rec.recommendation),
        displayed_action=rec.recommendation,
        has_position=has_position,
        calibration_scope=rec.calibration_scope,
        calibration_sample_size=rec.calibration_sample_size,
        composite_score=rec.composite_score,
        confidence=rec.confidence,
        probability_buy=rec.probability_buy,
        probability_sell=rec.probability_sell,
        probability_no_trade=rec.probability_no_trade,
        buy_threshold=rec.buy_threshold,
        sell_threshold=rec.sell_threshold,
        transaction_cost_pct=rec.transaction_cost_pct,
        expected_gross_edge_pct=rec.expected_gross_edge_pct,
        expected_net_edge_pct=rec.expected_net_edge_pct,
        uncertainty_pct=rec.uncertainty_pct,
        meta_trade_probability=rec.meta_trade_probability,
        meta_gate_applied=rec.meta_gate_applied,
        meta_trade_threshold=rec.meta_trade_threshold,
        meta_threshold_scope=rec.meta_threshold_scope,
        base_price=rec.last_price,
    )
    db.add(row)
    db.flush()
    return row


def persist_current_recommendations(db: Session) -> int:
    from app.db.models import PortfolioPositionORM
    from app.services.recommendation_engine import build_all_recommendations

    held = set(db.scalars(
        select(PortfolioPositionORM.asset_id).where(PortfolioPositionORM.quantity > 0)
    ).all())
    inserted = 0
    for rec in build_all_recommendations(db):
        before = db.scalar(
            select(func.count()).select_from(RecommendationRecordORM).where(
                RecommendationRecordORM.asset_id == rec.asset_id,
                RecommendationRecordORM.snapshot_at == rec.snapshot_at,
                RecommendationRecordORM.model_version == MODEL_VERSION,
            )
        ) or 0
        persist_recommendation(db, rec, has_position=rec.asset_id in held)
        inserted += int(before == 0 and rec.snapshot_at is not None)
    db.commit()
    return inserted


def _future_daily_closes(db: Session, row: RecommendationRecordORM) -> list[float]:
    # MAX(id) wybiera najnowszy zapis, gdy provider pozostawi kilka świec dnia.
    latest_per_day = (
        select(
            func.date(PricePointORM.timestamp).label("day"),
            func.max(PricePointORM.id).label("price_id"),
        )
        .where(
            PricePointORM.asset_id == row.asset_id,
            func.date(PricePointORM.timestamp) > row.snapshot_at.date(),
        )
        .group_by(func.date(PricePointORM.timestamp))
        .order_by(func.date(PricePointORM.timestamp).asc())
        .limit(20)
        .subquery()
    )
    return [float(value) for value in db.scalars(
        select(PricePointORM.close)
        .join(latest_per_day, PricePointORM.id == latest_per_day.c.price_id)
        .order_by(latest_per_day.c.day.asc())
    ).all()]


def _strategy_net_return(action: str, gross_return: float, cost: float) -> float:
    if action == "BUY":
        return gross_return - cost
    if action == "SELL":
        return -gross_return - cost
    return 0.0


def evaluate_recommendation_outcomes(db: Session, limit: int = 500) -> int:
    rows = db.scalars(
        select(RecommendationRecordORM)
        .where(RecommendationRecordORM.realized_return_20d_pct.is_(None))
        .order_by(RecommendationRecordORM.snapshot_at.asc())
        .limit(limit)
    ).all()
    changed = 0
    for row in rows:
        if not row.base_price or row.base_price <= 0:
            row.quality_flag = "missing_base_price"
            continue
        closes = _future_daily_closes(db, row)
        any_update = False
        for horizon in HORIZONS:
            realized_name = f"realized_return_{horizon}d_pct"
            strategy_name = f"strategy_net_return_{horizon}d_pct"
            if getattr(row, realized_name) is not None or len(closes) < horizon:
                continue
            gross = (closes[horizon - 1] / row.base_price - 1.0) * 100.0
            setattr(row, realized_name, round(gross, 6))
            setattr(
                row,
                strategy_name,
                round(_strategy_net_return(row.action, gross, row.transaction_cost_pct), 6),
            )
            any_update = True
        if row.realized_return_1d_pct is not None and abs(row.realized_return_1d_pct) > 35:
            row.quality_flag = "possible_corporate_action_1d"
        elif row.realized_return_5d_pct is not None and abs(row.realized_return_5d_pct) > 60:
            row.quality_flag = "possible_corporate_action_5d"
        elif row.realized_return_20d_pct is not None and abs(row.realized_return_20d_pct) > 100:
            row.quality_flag = "possible_corporate_action_20d"
        if any_update:
            row.evaluated_at = datetime.now(timezone.utc)
            changed += 1
    db.commit()
    return changed


def list_recommendation_records(
    db: Session,
    *,
    limit: int = 200,
    asset_id: str | None = None,
) -> list[RecommendationRecordORM]:
    stmt = select(RecommendationRecordORM)
    if asset_id:
        stmt = stmt.where(RecommendationRecordORM.asset_id == asset_id)
    return list(db.scalars(
        stmt.order_by(RecommendationRecordORM.snapshot_at.desc()).limit(min(max(limit, 1), 1000))
    ).all())
