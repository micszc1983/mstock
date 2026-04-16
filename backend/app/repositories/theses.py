from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import ThesisORM
from app.schemas.thesis import ThesisResponse


def insert_thesis(db: Session, thesis: ThesisResponse, source_snapshot_at, model_name: str = "thesis_v1") -> ThesisORM:
    row = ThesisORM(
        asset_id=thesis.asset_id,
        generated_at=thesis.generated_at,
        source_snapshot_at=source_snapshot_at,
        regime=thesis.regime,
        regime_confidence=thesis.regime_confidence,
        dominant_narrative=thesis.dominant_narrative,
        thesis_confidence=thesis.thesis_confidence,
        fragility_score=thesis.fragility_score,
        divergence_score=thesis.divergence_score,
        thesis=thesis.thesis,
        anti_thesis=thesis.anti_thesis,
        support_factors_json=json.dumps(thesis.support_factors, ensure_ascii=False),
        risk_factors_json=json.dumps(thesis.risk_factors, ensure_ascii=False),
        invalidation_conditions_json=json.dumps(thesis.invalidation_conditions, ensure_ascii=False),
        model_name=model_name,
    )
    db.add(row)
    db.flush()
    return row


def list_thesis_history(db: Session, asset_id: str, limit: int = 30) -> list[ThesisORM]:
    stmt = (
        select(ThesisORM)
        .where(ThesisORM.asset_id == asset_id)
        .order_by(ThesisORM.generated_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


def get_latest_thesis(db: Session, asset_id: str) -> ThesisORM | None:
    stmt = (
        select(ThesisORM)
        .where(ThesisORM.asset_id == asset_id)
        .order_by(ThesisORM.generated_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def delete_thesis_for_timestamp(db: Session, asset_id: str, generated_at) -> None:
    db.execute(
        delete(ThesisORM).where(
            ThesisORM.asset_id == asset_id,
            ThesisORM.generated_at == generated_at,
        )
    )
