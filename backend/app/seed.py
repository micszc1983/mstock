from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.asset_registry import ASSET_DEFINITIONS
from app.core.config import settings
from app.db.models import AssetORM, PricePointORM, ThesisORM
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
            # assets.json jest źródłem prawdy dla wbudowanego rejestru. Dzięki
            # pełnemu upsertowi korekty tickerów trafiają również do istniejącej DB.
            asset.symbol = a.symbol
            asset.name = a.name
            asset.type = a.type
            asset.currency = a.currency
            asset.sector = a.sector
            asset.description = a.description
            asset.price_symbol = a.price_symbol
            asset.news_symbol = a.news_symbol
            asset.news_term = a.news_term
            asset.metal_price_fn = a.metal_price_fn
    db.commit()

    # Produkcja nigdy nie dostaje syntetycznych notowań. Testy potrzebują jednak
    # stabilnego, offline'owego szeregu, żeby weryfikować cały pipeline.
    if settings.testing:
        _seed_test_market_data(db)

    # Sample newsy — ręcznie zredagowane, nie generowane losowo
    _seed_sample_news(db)


def _seed_test_market_data(db: Session) -> None:
    if db.query(PricePointORM).filter(PricePointORM.asset_id == "nvda").first():
        return

    start = (utc_now() - timedelta(days=200)).replace(hour=21, minute=0, second=0, microsecond=0)
    prices: list[PricePointORM] = []
    for day in range(80):
        close = 100.0 + day * 0.45 + ((day % 7) - 3) * 0.18
        open_price = close - 0.22
        prices.append(PricePointORM(
            asset_id="nvda",
            timestamp=start + timedelta(days=day),
            open=open_price,
            high=max(open_price, close) + 0.8,
            low=min(open_price, close) - 0.8,
            close=close,
            volume=1_000_000.0 + day * 2_500.0,
        ))
    db.add_all(prices)
    db.flush()

    # Teza ma historyczny punkt wejścia i pełne przyszłe okna 1/5/20 dni.
    # generated_at jest najnowsze, więc test pojedynczej ewaluacji wybiera ją
    # także po przebudowie bieżącego snapshotu.
    source_at = prices[35].timestamp
    db.add(ThesisORM(
        asset_id="nvda",
        generated_at=utc_now() + timedelta(minutes=1),
        source_snapshot_at=source_at,
        regime="risk_on",
        regime_confidence=0.78,
        dominant_narrative="ai_growth",
        thesis_confidence=0.76,
        fragility_score=24.0,
        divergence_score=12.0,
        thesis="Trend wzrostowy jest wspierany przez dodatni momentum.",
        anti_thesis="Spadek popytu może podważyć scenariusz.",
        support_factors_json='["trend", "momentum"]',
        risk_factors_json='["volatility"]',
        invalidation_conditions_json='["close below support"]',
        model_name="test_fixture_v1",
    ))
    db.commit()


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
