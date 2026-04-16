from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import HeuristicVsMLComparisonORM
from app.utils.datetime import now_utc


def insert_strategy_comparison(
    db: Session,
    asset_id: str,
    heuristic_accuracy_5d: float,
    ml_accuracy_5d: float,
    heuristic_avg_return_5d: float,
    ml_avg_return_5d: float,
    better_mode: str,
    sample_size: int,
) -> HeuristicVsMLComparisonORM:
    row = HeuristicVsMLComparisonORM(
        asset_id=asset_id,
        created_at=now_utc(),
        heuristic_accuracy_5d=heuristic_accuracy_5d,
        ml_accuracy_5d=ml_accuracy_5d,
        heuristic_avg_return_5d=heuristic_avg_return_5d,
        ml_avg_return_5d=ml_avg_return_5d,
        better_mode=better_mode,
        sample_size=sample_size,
    )
    db.add(row)
    db.flush()
    return row


def get_latest_strategy_comparison(db: Session, asset_id: str) -> HeuristicVsMLComparisonORM | None:
    return db.scalar(
        select(HeuristicVsMLComparisonORM)
        .where(HeuristicVsMLComparisonORM.asset_id == asset_id)
        .order_by(HeuristicVsMLComparisonORM.created_at.desc())
        .limit(1)
    )


def list_strategy_comparisons(db: Session, limit: int = 100) -> list[HeuristicVsMLComparisonORM]:
    return db.scalars(
        select(HeuristicVsMLComparisonORM)
        .order_by(HeuristicVsMLComparisonORM.created_at.desc())
        .limit(limit)
    ).all()
