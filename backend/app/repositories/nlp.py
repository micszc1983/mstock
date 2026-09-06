from __future__ import annotations

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.models import NewsNLPRunORM, NewsNarrativePredictionORM


def delete_nlp_for_news(db: Session, news_id: str) -> None:
    db.execute(delete(NewsNLPRunORM).where(NewsNLPRunORM.news_id == news_id))
    db.execute(delete(NewsNarrativePredictionORM).where(NewsNarrativePredictionORM.news_id == news_id))


def insert_nlp_run(
    db: Session,
    news_id: str,
    model_name: str,
    processed_at,
    sentiment_score: float,
    sentiment_label: str,
    sentiment_confidence: float,
    relevance_score: float,
    raw_output_json: str,
) -> NewsNLPRunORM:
    row = NewsNLPRunORM(
        news_id=news_id,
        model_name=model_name,
        processed_at=processed_at,
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        sentiment_confidence=sentiment_confidence,
        relevance_score=relevance_score,
        raw_output_json=raw_output_json,
    )
    db.add(row)
    db.flush()
    return row


def insert_narrative_prediction(
    db: Session,
    news_id: str,
    model_name: str,
    narrative_label: str,
    score: float,
    confidence: float,
) -> NewsNarrativePredictionORM:
    row = NewsNarrativePredictionORM(
        news_id=news_id,
        model_name=model_name,
        narrative_label=narrative_label,
        score=score,
        confidence=confidence,
    )
    db.add(row)
    db.flush()
    return row


def get_latest_nlp_run(db: Session, news_id: str) -> NewsNLPRunORM | None:
    stmt = (
        select(NewsNLPRunORM)
        .where(NewsNLPRunORM.news_id == news_id)
        .order_by(NewsNLPRunORM.processed_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def list_narrative_predictions(
    db: Session,
    news_id: str,
    model_name: str | None = None,
) -> list[NewsNarrativePredictionORM]:
    stmt = select(NewsNarrativePredictionORM).where(NewsNarrativePredictionORM.news_id == news_id)
    if model_name is not None:
        stmt = stmt.where(NewsNarrativePredictionORM.model_name == model_name)
    stmt = stmt.order_by(NewsNarrativePredictionORM.score.desc())
    return db.scalars(stmt).all()
