from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.asset_registry import ASSET_DEFINITIONS
from app.db.models import AssetORM, PricePointORM
from app.repositories.news import upsert_news_item
from app.schemas.common import NarrativeLabel
from app.schemas.news import NewsItem


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def seed_database(db: Session) -> None:
    """
    Wstawia definicje aktywów z assets.json (idempotentne).
    NIE generuje fałszywych cen — ceny pobierane wyłącznie od providerów.
    """
    # Upsert każde aktywo z assets.json — wstawia nowe, aktualizuje istniejące
    for a in ASSET_DEFINITIONS:
        asset = db.get(AssetORM, a.id)
        if asset is None:
            db.add(AssetORM(
                id=a.id,
                symbol=a.symbol,
                name=a.name,
                type=a.type,
                currency=a.currency,
                sector=a.sector,
                description=a.description,
                price_symbol=a.price_symbol,
                news_symbol=a.news_symbol,
                news_term=a.news_term,
                metal_price_fn=a.metal_price_fn,
            ))
        else:
            # Backfill currency + provider config dla istniejących aktywów
            if getattr(asset, "currency", None) != a.currency:
                asset.currency = a.currency
            if not asset.price_symbol and a.price_symbol:
                asset.price_symbol = a.price_symbol
            if not asset.news_symbol and a.news_symbol:
                asset.news_symbol = a.news_symbol
            if not asset.news_term and a.news_term:
                asset.news_term = a.news_term
            if not asset.metal_price_fn and a.metal_price_fn:
                asset.metal_price_fn = a.metal_price_fn
    db.commit()

    # Sample newsy — ręcznie zredagowane, nie generowane losowo
    _seed_sample_news(db)


def _seed_sample_news(db: Session) -> None:
    now = utc_now()
    samples: list[NewsItem] = []

    nvda = next((a for a in ASSET_DEFINITIONS if a.id == "nvda"), None)
    gold = next((a for a in ASSET_DEFINITIONS if a.id == "gold"), None)
    kghm = next((a for a in ASSET_DEFINITIONS if a.id == "kghm"), None)

    if nvda:
        samples.append(NewsItem(
            id="n1", asset_id="nvda",
            published_at=now - timedelta(hours=6),
            source="MarketWire",
            title="AI server demand remains strong, but margin concerns rise",
            body="Analysts still see strong demand, though margin discipline is back in focus.",
            sentiment_score=0.35, impact_score=0.82,
            narratives={NarrativeLabel.AI_GROWTH: 0.78, NarrativeLabel.MARGIN_PRESSURE: 0.66},
        ))
    if gold:
        samples.append(NewsItem(
            id="g1", asset_id="gold",
            published_at=now - timedelta(hours=10),
            source="CommoditiesDesk",
            title="Gold holds firm as safe-haven demand offsets stronger dollar",
            body="Investors continue to treat gold as a defensive asset amid geopolitical uncertainty.",
            sentiment_score=0.29, impact_score=0.77,
            narratives={NarrativeLabel.SAFE_HAVEN: 0.88, NarrativeLabel.DOLLAR_PRESSURE: 0.49},
        ))
    if kghm:
        samples += [
            NewsItem(
                id="kghm1", asset_id="kghm",
                published_at=now - timedelta(days=2, hours=3),
                source="PAP", title="KGHM podnosi produkcję miedzi — wyniki powyżej oczekiwań",
                body="KGHM Polska Miedź poinformował o wzroście produkcji miedzi elektrolitycznej w Q1.",
                sentiment_score=0.55, impact_score=0.78,
                narratives={NarrativeLabel.DEMAND_STRENGTH: 0.74, NarrativeLabel.INDUSTRIAL_DEMAND: 0.66},
            ),
            NewsItem(
                id="kghm2", asset_id="kghm",
                published_at=now - timedelta(days=5, hours=8),
                source="Parkiet", title="KGHM: presja kosztów energii wpływa na marże",
                body="Rosnące koszty energii elektrycznej w Polsce obciążają marże KGHM.",
                sentiment_score=-0.28, impact_score=0.71,
                narratives={NarrativeLabel.MARGIN_PRESSURE: 0.81, NarrativeLabel.REGULATION_RISK: 0.42},
            ),
        ]

    for item in samples:
        upsert_news_item(db, item)
    db.commit()
