from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NewsItemORM, NewsNarrativeORM
from app.schemas.news import NewsItem


_INVISIBLE_TITLE_CHARS = re.compile(r"[\u200b-\u200d\u2060\ufeff]")


def _clean_title(value: str) -> str:
    return _INVISIBLE_TITLE_CHARS.sub("", value).strip()


def list_news(db: Session, asset_id: str, limit: int | None = None) -> list[NewsItemORM]:
    stmt = select(NewsItemORM).where(NewsItemORM.asset_id == asset_id).order_by(NewsItemORM.published_at.desc())
    rows = db.scalars(stmt).all()
    return rows[:limit] if limit is not None else rows


def upsert_news_item(db: Session, item: NewsItem) -> bool:
    existing = db.get(NewsItemORM, item.id)
    if existing:
        existing.source = item.source
        existing.title = _clean_title(item.title)
        existing.body = item.body
        existing.published_at = item.published_at
        existing.sentiment_score = item.sentiment_score
        existing.impact_score = item.impact_score
        existing.narratives.clear()
        for label, score in item.narratives.items():
            existing.narratives.append(NewsNarrativeORM(narrative_label=label.value, score=score))
        return False

    db_item = NewsItemORM(
        id=item.id,
        asset_id=item.asset_id,
        published_at=item.published_at,
        source=item.source,
        title=_clean_title(item.title),
        body=item.body,
        sentiment_score=item.sentiment_score,
        impact_score=item.impact_score,
    )
    for label, score in item.narratives.items():
        db_item.narratives.append(NewsNarrativeORM(narrative_label=label.value, score=score))
    db.add(db_item)
    return True
