from __future__ import annotations

from app.schemas.asset import Asset, PricePoint
from app.schemas.common import AssetType, NarrativeLabel
from app.schemas.news import NewsItem
from app.services.analytics import (
    build_overview,
    compute_divergence_score,
    compute_sentiment_score,
    compute_trend_score,
    dominant_narrative,
)


def make_prices() -> list[PricePoint]:
    prices = []
    base = 100.0
    for idx in range(30):
        close = base + idx * 1.5
        prices.append(
            PricePoint(
                timestamp=f"2026-01-{idx+1:02d}T00:00:00+00:00",
                open=close - 0.5,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000 + idx * 10,
            )
        )
    return prices


def make_news() -> list[NewsItem]:
    return [
        NewsItem(
            id="1",
            asset_id="nvda",
            published_at="2026-01-10T10:00:00+00:00",
            source="A",
            title="AI growth stays strong",
            body="GPU demand and AI capex remain strong",
            sentiment_score=0.6,
            impact_score=0.8,
            narratives={NarrativeLabel.AI_GROWTH: 0.9, NarrativeLabel.DEMAND_STRENGTH: 0.6},
        ),
        NewsItem(
            id="2",
            asset_id="nvda",
            published_at="2026-01-11T10:00:00+00:00",
            source="B",
            title="Margin pressure appears",
            body="Some pricing pressure is visible",
            sentiment_score=-0.2,
            impact_score=0.6,
            narratives={NarrativeLabel.MARGIN_PRESSURE: 0.8},
        ),
    ]


def test_trend_score_positive_for_uptrend():
    score = compute_trend_score(make_prices())
    assert score > 0


def test_sentiment_and_dominant_narrative():
    news = make_news()
    assert compute_sentiment_score(news) > 0
    assert dominant_narrative(news) in {NarrativeLabel.AI_GROWTH, NarrativeLabel.MARGIN_PRESSURE}


def test_overview_builds_expected_fields():
    asset = Asset(id="nvda", symbol="NVDA", name="NVIDIA", type=AssetType.STOCK)
    overview = build_overview(asset, make_prices(), make_news())
    assert overview.asset.id == "nvda"
    assert overview.last_price > 0
    assert 0 <= overview.fragility_score <= 100


def test_divergence_is_bounded():
    score = compute_divergence_score(make_prices(), make_news())
    assert 0 <= score <= 100
