from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EarningsCallAnalysisORM, EarningsORM


def upsert_earnings_analysis(db: Session, earnings_id: int, **fields) -> EarningsCallAnalysisORM:
    """Wstaw lub zaktualizuj analizę LLM dla danego rekordu wyników."""
    row = db.scalar(
        select(EarningsCallAnalysisORM)
        .where(EarningsCallAnalysisORM.earnings_id == earnings_id)
    )
    if row is None:
        row = EarningsCallAnalysisORM(earnings_id=earnings_id, **fields)
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
        row.analyzed_at = datetime.now(timezone.utc)
    db.flush()
    return row


def get_analysis_for_earnings(db: Session, earnings_id: int) -> Optional[EarningsCallAnalysisORM]:
    return db.scalar(
        select(EarningsCallAnalysisORM)
        .where(EarningsCallAnalysisORM.earnings_id == earnings_id)
    )


def list_analyses_for_asset(db: Session, asset_id: str, limit: int = 8) -> list[EarningsCallAnalysisORM]:
    stmt = (
        select(EarningsCallAnalysisORM)
        .where(EarningsCallAnalysisORM.asset_id == asset_id)
        .order_by(EarningsCallAnalysisORM.analyzed_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


def get_latest_llm_sentiment(db: Session, asset_id: str, max_days: int = 90) -> Optional[float]:
    """
    Zwraca llm_sentiment_score z ostatniej analizy (< max_days temu).
    Używane przez recommendation_engine jako sygnał fundamentalny.
    """
    cutoff_date = date.today() - timedelta(days=max_days)
    row = db.scalar(
        select(EarningsCallAnalysisORM)
        .join(EarningsORM, EarningsCallAnalysisORM.earnings_id == EarningsORM.id)
        .where(
            EarningsCallAnalysisORM.asset_id == asset_id,
            EarningsORM.report_date >= cutoff_date,
        )
        .order_by(EarningsORM.report_date.desc())
        .limit(1)
    )
    return row.llm_sentiment_score if row is not None else None
