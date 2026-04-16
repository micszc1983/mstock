from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import ThesisOutcomeORM


def insert_outcome(
    db: Session,
    thesis_id: int,
    asset_id: str,
    evaluated_at,
    horizon: str,
    base_price: float,
    realized_price: float,
    realized_return_pct: float,
    was_directionally_correct: bool,
    outcome_label: str,
) -> ThesisOutcomeORM:
    row = ThesisOutcomeORM(
        thesis_id=thesis_id,
        asset_id=asset_id,
        evaluated_at=evaluated_at,
        horizon=horizon,
        base_price=base_price,
        realized_price=realized_price,
        realized_return_pct=realized_return_pct,
        was_directionally_correct=was_directionally_correct,
        outcome_label=outcome_label,
    )
    db.add(row)
    db.flush()
    return row


def delete_outcomes_for_thesis(db: Session, thesis_id: int) -> None:
    db.execute(delete(ThesisOutcomeORM).where(ThesisOutcomeORM.thesis_id == thesis_id))


def list_outcomes_for_asset(db: Session, asset_id: str, limit: int = 100) -> list[ThesisOutcomeORM]:
    stmt = (
        select(ThesisOutcomeORM)
        .where(ThesisOutcomeORM.asset_id == asset_id)
        .order_by(ThesisOutcomeORM.evaluated_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


def list_outcomes_for_thesis(db: Session, thesis_id: int) -> list[ThesisOutcomeORM]:
    stmt = (
        select(ThesisOutcomeORM)
        .where(ThesisOutcomeORM.thesis_id == thesis_id)
        .order_by(ThesisOutcomeORM.horizon.asc())
    )
    return db.scalars(stmt).all()
