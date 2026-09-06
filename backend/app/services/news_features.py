"""Validated news inputs used by features, theses and recommendations."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import NewsItemORM, NewsNarrativePredictionORM, NewsNLPRunORM
from app.mappers import news_to_schema
from app.schemas.common import NarrativeLabel
from app.schemas.news import NewsItem
from app.utils.datetime import ensure_utc, now_utc


def latest_nlp_runs(
    db: Session,
    news_ids: list[str],
    *,
    as_of: datetime | None = None,
) -> dict[str, NewsNLPRunORM]:
    if not news_ids:
        return {}
    stmt = select(NewsNLPRunORM).where(NewsNLPRunORM.news_id.in_(news_ids))
    if as_of is not None:
        stmt = stmt.where(NewsNLPRunORM.processed_at <= ensure_utc(as_of))
    runs = db.scalars(
        stmt.order_by(NewsNLPRunORM.processed_at.desc(), NewsNLPRunORM.id.desc())
    ).all()
    latest: dict[str, NewsNLPRunORM] = {}
    for run in runs:
        latest.setdefault(run.news_id, run)
    return latest


def list_news_for_analysis(
    db: Session,
    asset_id: str,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    min_relevance: float | None = None,
) -> list[NewsItem]:
    """Return only NLP-enriched and sufficiently relevant recent articles.

    Provider sentiment is never used as a silent fallback. Impact is reduced by
    both relevance and sentiment confidence, so uncertain text cannot dominate.
    """
    anchor = ensure_utc(as_of) if as_of is not None else now_utc()
    threshold = settings.news_min_relevance if min_relevance is None else min_relevance
    rows = list(db.scalars(
        select(NewsItemORM).where(
            NewsItemORM.asset_id == asset_id,
            NewsItemORM.published_at > anchor - timedelta(days=lookback_days),
            NewsItemORM.published_at <= anchor,
        ).order_by(NewsItemORM.published_at.asc())
    ).all())
    # NLP is a deterministic transformation of text already public at anchor;
    # its processing timestamp must not hide same-session reports enriched a
    # few minutes after close. Strict training boundaries live in PIT store.
    latest = latest_nlp_runs(db, [row.id for row in rows])
    accepted = [row for row in rows if row.id in latest and latest[row.id].relevance_score >= threshold]
    if not accepted:
        return []

    predictions = db.scalars(
        select(NewsNarrativePredictionORM).where(
            NewsNarrativePredictionORM.news_id.in_([row.id for row in accepted])
        ).order_by(NewsNarrativePredictionORM.score.desc())
    ).all()
    narratives_by_news: dict[str, dict[NarrativeLabel, float]] = {}
    for pred in predictions:
        run = latest.get(pred.news_id)
        if run is None or pred.model_name != run.model_name:
            continue
        try:
            label = NarrativeLabel(pred.narrative_label)
        except ValueError:
            continue
        narratives_by_news.setdefault(pred.news_id, {})[label] = float(pred.score)

    result: list[NewsItem] = []
    for row in accepted:
        run = latest[row.id]
        relevance = max(0.0, min(1.0, float(run.relevance_score)))
        confidence = max(0.0, min(1.0, float(run.sentiment_confidence)))
        effective_impact = max(0.0, min(1.0, float(row.impact_score or 0.0) * relevance * confidence))
        result.append(news_to_schema(row).model_copy(update={
            "sentiment_score": float(run.sentiment_score),
            "impact_score": effective_impact,
            "narratives": narratives_by_news.get(row.id, {}),
        }))
    return result
