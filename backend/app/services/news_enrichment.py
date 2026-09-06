from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, exists
from sqlalchemy.orm import Session

from app.db.models import NewsItemORM, NewsNLPRunORM
from app.mappers import asset_to_schema, news_to_schema
from app.repositories.assets import get_asset
from app.repositories.nlp import (
    get_latest_nlp_run,
    insert_narrative_prediction,
    insert_nlp_run,
    list_narrative_predictions,
)
from app.schemas.common import AssetType
from app.schemas.nlp import NewsNLPResponse, NewsNarrativePredictionResponse
from app.services.nlp import build_nlp_payload
from app.services.nlp_backends.registry import get_nlp_backend
from app.core.config import settings
from app.utils.datetime import now_utc


def enrich_news_for_asset(
    db: Session,
    asset_id: str,
    limit: int = 100,
    *,
    upgrade_limit: int | None = None,
) -> int:
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        return 0

    asset = asset_to_schema(asset_row)

    model_name = get_nlp_backend().model_name
    has_any_run = exists().where(NewsNLPRunORM.news_id == NewsItemORM.id)
    has_current_run = exists().where(
        NewsNLPRunORM.news_id == NewsItemORM.id,
        NewsNLPRunORM.model_name == model_name,
    )

    # Najpierw zawsze nowe artykuły. Potem mała, kontrolowana paczka świeżych
    # artykułów przetworzonych starszym modelem — bez blokowania schedulera.
    new_rows = list(db.scalars(
        select(NewsItemORM)
        .where(
            NewsItemORM.asset_id == asset_id,
            ~has_any_run,
        )
        .order_by(NewsItemORM.published_at.desc())
        .limit(limit)
    ).all())
    upgrade_budget = settings.nlp_upgrade_per_asset_cycle if upgrade_limit is None else upgrade_limit
    upgrade_limit = min(
        max(0, limit - len(new_rows)),
        max(0, upgrade_budget),
    )
    upgrade_rows = list(db.scalars(
        select(NewsItemORM)
        .where(
            NewsItemORM.asset_id == asset_id,
            NewsItemORM.published_at >= now_utc() - timedelta(days=settings.nlp_reprocess_days),
            has_any_run,
            ~has_current_run,
        )
        .order_by(NewsItemORM.published_at.desc())
        .limit(upgrade_limit)
    ).all()) if upgrade_limit else []

    enriched = 0
    for row in [*new_rows, *upgrade_rows]:
        item = news_to_schema(row)
        text = f"{item.title}\n\n{item.body}"
        payload = build_nlp_payload(text, asset.name, asset.symbol, AssetType(asset.type), sector=asset_row.sector)
        insert_nlp_run(
            db,
            news_id=item.id,
            model_name=payload["model_name"],
            processed_at=payload["processed_at"],
            sentiment_score=payload["sentiment_score"],
            sentiment_label=payload["sentiment_label"],
            sentiment_confidence=payload["sentiment_confidence"],
            relevance_score=payload["relevance_score"],
            raw_output_json=payload["raw_output_json"],
        )
        for pred in payload["narratives"]:
            insert_narrative_prediction(
                db,
                news_id=item.id,
                model_name=payload["model_name"],
                narrative_label=pred["narrative_label"],
                score=pred["score"],
                confidence=pred["confidence"],
            )
        enriched += 1
    db.commit()
    return enriched


def get_news_nlp_response(db: Session, news_id: str) -> NewsNLPResponse | None:
    run = get_latest_nlp_run(db, news_id)
    if run is None:
        return None
    preds = list_narrative_predictions(db, news_id, model_name=run.model_name)
    return NewsNLPResponse(
        news_id=run.news_id,
        model_name=run.model_name,
        processed_at=run.processed_at,
        sentiment_score=run.sentiment_score,
        sentiment_label=run.sentiment_label,
        sentiment_confidence=run.sentiment_confidence,
        relevance_score=run.relevance_score,
        raw_output_json=run.raw_output_json,
        narratives=[
            NewsNarrativePredictionResponse(
                news_id=p.news_id,
                model_name=p.model_name,
                narrative_label=p.narrative_label,
                score=p.score,
                confidence=p.confidence,
            )
            for p in preds
        ],
    )
