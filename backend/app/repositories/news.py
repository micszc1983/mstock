from __future__ import annotations

import re
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NewsItemORM, NewsNarrativeORM
from app.schemas.news import NewsItem


_INVISIBLE_TITLE_CHARS = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
_NON_WORD_TITLE_CHARS = re.compile(r"[^a-z0-9ąćęłńóśźż]+", re.IGNORECASE)


def _clean_title(value: str) -> str:
    return _INVISIBLE_TITLE_CHARS.sub("", value).strip()


def _title_fingerprint(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", _clean_title(value)).casefold()
    normalized = re.sub(
        r"\s*[-–—|]\s*(bankier(?:\.pl)?|parkiet(?:\.com)?|pap(?: mediaroom)?|stockwatch(?:\.pl)?)\s*$",
        "",
        normalized,
    )
    return " ".join(_NON_WORD_TITLE_CHARS.sub(" ", normalized).split())


def _same_story(left: str, right: str) -> bool:
    left_fp, right_fp = _title_fingerprint(left), _title_fingerprint(right)
    if not left_fp or not right_fp:
        return False
    if left_fp == right_fp:
        return True
    # Dostawcy często dopisują nazwę serwisu lub pojedynczy prefiks.
    if min(len(left_fp), len(right_fp)) < 32:
        return False
    return SequenceMatcher(None, left_fp, right_fp).ratio() >= 0.94


def list_news(db: Session, asset_id: str, limit: int | None = None) -> list[NewsItemORM]:
    stmt = select(NewsItemORM).where(NewsItemORM.asset_id == asset_id).order_by(NewsItemORM.published_at.desc())
    rows = db.scalars(stmt).all()
    return rows[:limit] if limit is not None else rows


def upsert_news_item(db: Session, item: NewsItem) -> bool:
    # Provider potrafi zwrócić ten sam artykuł kilka razy w jednej paczce.
    # Drugi obiekt może być jeszcze w stanie pending, więc samo db.get()
    # nie zawsze zobaczy go przed flush i PostgreSQL odrzuci cały batch.
    existing = next(
        (
            row for row in db.new
            if isinstance(row, NewsItemORM) and row.id == item.id
        ),
        None,
    )
    if existing is None:
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

    # Ten sam artykuł bywa zwracany przez RSS, NewsAPI i agregator pod różnymi
    # identyfikatorami. Deduplikuj w obrębie aktywa i trzydniowego okna.
    candidates = [
        row for row in db.new
        if isinstance(row, NewsItemORM) and row.asset_id == item.asset_id
    ]
    candidates.extend(db.scalars(
        select(NewsItemORM).where(
            NewsItemORM.asset_id == item.asset_id,
            NewsItemORM.published_at >= item.published_at - timedelta(days=3),
            NewsItemORM.published_at <= item.published_at + timedelta(days=3),
        ).order_by(NewsItemORM.published_at.desc()).limit(250)
    ).all())
    duplicate = next((row for row in candidates if _same_story(row.title, item.title)), None)
    if duplicate is not None:
        if len(item.body or "") > len(duplicate.body or ""):
            duplicate.body = item.body
        duplicate.impact_score = max(float(duplicate.impact_score or 0.0), item.impact_score)
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
