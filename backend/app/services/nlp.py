"""
nlp.py — fasada warstwy NLP.

Reszta systemu używa wyłącznie tej fasady.
Backend (heuristic / transformer) jest transparentny.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.schemas.common import AssetType
from app.services.nlp_backends.registry import get_nlp_backend


def classify_sentiment(text: str) -> dict:
    backend = get_nlp_backend()
    return backend.classify_sentiment(text, "")


def classify_narratives(text: str, asset_type: AssetType) -> list[dict]:
    backend = get_nlp_backend()
    return backend.classify_narratives(text, "", asset_type)


def score_relevance(text: str, asset_name: str, symbol: str) -> float:
    backend = get_nlp_backend()
    return backend.score_relevance(text, "", asset_name, symbol, None)


def build_nlp_payload(
    text: str,
    asset_name: str,
    symbol: str,
    asset_type: AssetType,
    sector: str | None = None,
) -> dict:
    backend = get_nlp_backend()

    # Rozdziel tekst na title + body przy newline, albo traktuj jako body
    parts = text.split("\n\n", 1)
    title = parts[0].strip()
    body  = parts[1].strip() if len(parts) > 1 else ""

    sentiment  = backend.classify_sentiment(title, body)
    narratives = backend.classify_narratives(title, body, asset_type)
    relevance  = backend.score_relevance(title, body, asset_name, symbol, sector)

    return {
        "model_name":            backend.model_name,
        "processed_at":          datetime.now(timezone.utc),
        "sentiment_score":       sentiment["score"],
        "sentiment_label":       sentiment["label"],
        "sentiment_confidence":  sentiment["confidence"],
        "relevance_score":       relevance,
        "raw_output_json": json.dumps(
            {
                "text_preview": text[:200],
                "sentiment":    sentiment,
                "narratives":   narratives,
                "relevance_score": relevance,
                "backend":      backend.model_name,
            },
            ensure_ascii=False,
        ),
        "narratives": narratives,
    }
