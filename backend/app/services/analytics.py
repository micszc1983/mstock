from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.schemas.asset import Asset, PricePoint
from app.schemas.common import AssetType, NarrativeLabel, RegimeLabel
from app.schemas.news import NarrativePoint, NewsItem
from app.core.config import weights as W
from app.schemas.thesis import AssetOverview, BreakMonitorItem, BreakMonitorResponse, ThesisResponse
from app.utils.datetime import ensure_utc, now_utc


def utc_now() -> datetime:
    return now_utc()


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def compute_trend_score(prices: List[PricePoint]) -> float:
    closes = [p.close for p in prices]
    if len(closes) < 21:
        return 0.0
    ema_5 = ema(closes, 5)[-1]
    ema_20 = ema(closes, 20)[-1]
    last = closes[-1]
    ret_5 = pct_change(closes[-1], closes[-6])
    ret_20 = pct_change(closes[-1], closes[-21])

    w = W.TREND_EMA_ABOVE_20_W
    w2 = W.TREND_EMA5_VS_EMA20_W
    score = 0.0
    score += w if last > ema_20 else -w
    score += w2 if ema_5 > ema_20 else -w2
    score += clamp(ret_5 * W.TREND_RET5_SCALE, -20, 20)
    score += clamp(ret_20, -W.TREND_RET20_CLAMP, W.TREND_RET20_CLAMP)
    return clamp(score, -100, 100)


def compute_sentiment_score(news_items: List[NewsItem]) -> float:
    if not news_items:
        return 0.0
    weighted_sum = sum(item.sentiment_score * item.impact_score for item in news_items)
    total_weight = sum(item.impact_score for item in news_items)
    if total_weight == 0:
        return 0.0
    return clamp((weighted_sum / total_weight) * 100.0, -100.0, 100.0)


def aggregate_narratives(news_items: List[NewsItem]) -> Dict[NarrativeLabel, float]:
    scores: Dict[NarrativeLabel, float] = {}
    for item in news_items:
        for label, score in item.narratives.items():
            scores[label] = scores.get(label, 0.0) + (score * item.impact_score)
    total = sum(scores.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in scores.items()}


def dominant_narrative(news_items: List[NewsItem]) -> Optional[NarrativeLabel]:
    agg = aggregate_narratives(news_items)
    if not agg:
        return None
    return max(agg, key=agg.get)


def compute_narrative_shift_score(news_items: List[NewsItem]) -> float:
    if len(news_items) < 2:
        return 0.0
    sorted_items = sorted(news_items, key=lambda x: ensure_utc(x.published_at))
    midpoint = len(sorted_items) // 2
    older = aggregate_narratives(sorted_items[:midpoint])
    newer = aggregate_narratives(sorted_items[midpoint:])
    labels = set(older.keys()) | set(newer.keys())
    total_diff = sum(abs(newer.get(label, 0.0) - older.get(label, 0.0)) for label in labels)
    return clamp(total_diff * 100.0, 0.0, 100.0)


def compute_regime(asset: Asset, prices: List[PricePoint], sentiment_score: float) -> tuple[RegimeLabel, float]:
    closes = [p.close for p in prices]
    if len(closes) < 21:
        return RegimeLabel.RANGE_BOUND, 0.4

    ret_5 = pct_change(closes[-1], closes[-6])
    ret_20 = pct_change(closes[-1], closes[-21])
    daily_returns = [pct_change(closes[i], closes[i - 1]) for i in range(1, len(closes))]
    vol = sum(abs(x) for x in daily_returns[-10:]) / max(1, len(daily_returns[-10:]))

    if asset.type == AssetType.METAL:
        if sentiment_score > 15 and ret_20 > 3:
            return RegimeLabel.SAFE_HAVEN, 0.73
        if vol > 2.4:
            return RegimeLabel.MACRO_DRIVEN, 0.66
        return RegimeLabel.RANGE_BOUND, 0.58

    if ret_20 > 8 and sentiment_score > 10:
        return RegimeLabel.RISK_ON, 0.78
    if ret_5 < -4 and sentiment_score < -10:
        return RegimeLabel.RISK_OFF, 0.75
    if vol > 2.2:
        return RegimeLabel.EARNINGS_DRIVEN, 0.63
    return RegimeLabel.RANGE_BOUND, 0.57


def compute_divergence_score(prices: List[PricePoint], news_items: List[NewsItem]) -> float:
    if len(prices) < 6:
        return 0.0
    price_move = pct_change(prices[-1].close, prices[-6].close)
    sentiment = compute_sentiment_score(news_items) / 100.0
    dominant = dominant_narrative(news_items)

    narrative_bias = 0.0
    positive_narratives = {
        NarrativeLabel.AI_GROWTH,
        NarrativeLabel.DEMAND_STRENGTH,
        NarrativeLabel.SAFE_HAVEN,
        NarrativeLabel.CENTRAL_BANK_BUYING,
        NarrativeLabel.INDUSTRIAL_DEMAND,
    }
    negative_narratives = {
        NarrativeLabel.MARGIN_PRESSURE,
        NarrativeLabel.DEMAND_SLOWDOWN,
        NarrativeLabel.REGULATION_RISK,
        NarrativeLabel.VALUATION_STRETCH,
        NarrativeLabel.RATES_PRESSURE,
        NarrativeLabel.DOLLAR_PRESSURE,
    }

    if dominant in positive_narratives:
        narrative_bias = 0.5
    elif dominant in negative_narratives:
        narrative_bias = -0.5

    divergence = abs((price_move / 10.0) - sentiment) + abs((price_move / 10.0) - narrative_bias)
    return clamp(divergence * 35.0, 0.0, 100.0)


def compute_fragility_score(prices: List[PricePoint], news_items: List[NewsItem]) -> float:
    shift = compute_narrative_shift_score(news_items)
    divergence = compute_divergence_score(prices, news_items)
    sentiment = abs(compute_sentiment_score(news_items))
    raw = (W.FRAGILITY_SHIFT_W * shift) + (W.FRAGILITY_DIVERGENCE_W * divergence) + (W.FRAGILITY_SENTIMENT_W * (100 - sentiment))
    return clamp(raw, 0.0, 100.0)


def build_overview(asset: Asset, prices: List[PricePoint], news_items: List[NewsItem]) -> AssetOverview:
    closes = [p.close for p in prices]
    sentiment = compute_sentiment_score(news_items)
    regime, regime_confidence = compute_regime(asset, prices, sentiment)

    return AssetOverview(
        asset=asset,
        last_price=round(closes[-1], 2),
        price_change_1d_pct=round(pct_change(closes[-1], closes[-2]), 2),
        price_change_5d_pct=round(pct_change(closes[-1], closes[-6]), 2),
        price_change_20d_pct=round(pct_change(closes[-1], closes[-21]), 2),
        trend_score=round(compute_trend_score(prices), 2),
        sentiment_score=round(sentiment, 2),
        narrative_shift_score=round(compute_narrative_shift_score(news_items), 2),
        divergence_score=round(compute_divergence_score(prices, news_items), 2),
        fragility_score=round(compute_fragility_score(prices, news_items), 2),
        regime=regime,
        regime_confidence=round(regime_confidence * 100, 2),
        dominant_narrative=dominant_narrative(news_items),
    )


def build_narrative_history(news_items: List[NewsItem], days: int = 7) -> List[NarrativePoint]:
    sorted_news = sorted(news_items, key=lambda n: ensure_utc(n.published_at))
    result: List[NarrativePoint] = []
    now_utc = utc_now()

    for day_offset in range(days - 1, -1, -1):
        day_start = (now_utc - timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        bucket = [item for item in sorted_news if day_start <= ensure_utc(item.published_at) < day_end]
        agg = aggregate_narratives(bucket)
        result.append(
            NarrativePoint(date=day_start, narrative_scores={label.value: round(score, 4) for label, score in agg.items()})
        )
    return result


def make_thesis(asset: Asset, prices: List[PricePoint], news_items: List[NewsItem]) -> ThesisResponse:
    trend = compute_trend_score(prices)
    sentiment = compute_sentiment_score(news_items)
    dom_narr = dominant_narrative(news_items)
    shift = compute_narrative_shift_score(news_items)
    divergence = compute_divergence_score(prices, news_items)
    fragility = compute_fragility_score(prices, news_items)
    regime, regime_conf = compute_regime(asset, prices, sentiment)

    support_factors: List[str] = []
    risk_factors: List[str] = []
    invalidation_conditions: List[str] = []

    if trend > 20:
        support_factors.append("Trend techniczny pozostaje dodatni w horyzoncie krótkim i średnim.")
    else:
        risk_factors.append("Trend techniczny nie daje jeszcze silnego potwierdzenia.")

    if sentiment > 10:
        support_factors.append("News flow jest netto dodatni po uwzględnieniu wagi informacji.")
    elif sentiment < -10:
        risk_factors.append("News flow jest wyraźnie negatywny i może ciążyć na wycenie.")

    if shift > 35:
        risk_factors.append("Narracja rynkowa szybko się zmienia, co zwiększa niepewność tezy.")

    if divergence > 45:
        risk_factors.append("Pojawia się rozjazd między ceną, sentymentem i dominującą narracją.")

    if dom_narr is not None:
        support_factors.append(f"Dominująca narracja to: {dom_narr.value}.")

    closes = [p.close for p in prices]
    ema20 = ema(closes, 20)[-1] if len(closes) >= 20 else closes[-1]

    invalidation_conditions.append(f"Cena zamknie się wyraźnie poniżej średniej 20-okresowej ({ema20:.2f}).")
    invalidation_conditions.append("Sentyment 3-7 dniowy spadnie poniżej poziomu neutralnego.")
    invalidation_conditions.append("Narracja przeciwna zyska przewagę w najnowszym news flow.")

    narrative_text = dom_narr.value.replace("_", " ") if dom_narr else "neutralnej narracji"

    if divergence > 55:
        thesis = (
            f"Rynek dla {asset.name} utrzymuje jeszcze elementy narracji '{narrative_text}', "
            f"ale rosnący rozjazd między ceną, sentymentem i przepływem informacji sugeruje, "
            f"że obecny ruch może być mniej trwały, niż wygląda na pierwszy rzut oka."
        )
        anti_thesis = (
            f"Mimo obecnych niespójności {asset.name} może kontynuować ruch, jeśli reżim {regime.value} "
            f"pozostanie aktywny, a kolejne informacje ponownie zsynchronizują narrację z zachowaniem ceny."
        )
    else:
        thesis = (
            f"{asset.name} pozostaje wspierany przez względnie spójny układ techniczny i informacyjny, "
            f"z dominującą narracją '{narrative_text}'."
        )
        anti_thesis = (
            f"Pozytywny obraz dla {asset.name} może zostać podważony, jeśli poprawa nastrojów okaże się płytka "
            f"lub rynek zacznie bardziej dyskontować ryzyka drugiego rzędu."
        )

    thesis_confidence = clamp(
        (max(trend, 0) * W.THESIS_TREND_W)
        + (max(sentiment, 0) * W.THESIS_SENTIMENT_W)
        + ((100 - divergence) * W.THESIS_DIVERGENCE_W)
        + ((100 - fragility) * W.THESIS_FRAGILITY_W),
        0.0,
        100.0,
    )

    return ThesisResponse(
        asset_id=asset.id,
        generated_at=utc_now(),
        regime=regime,
        regime_confidence=round(regime_conf * 100, 2),
        dominant_narrative=dom_narr,
        thesis_confidence=round(thesis_confidence, 2),
        fragility_score=round(fragility, 2),
        divergence_score=round(divergence, 2),
        thesis=thesis,
        anti_thesis=anti_thesis,
        support_factors=support_factors,
        risk_factors=risk_factors,
        invalidation_conditions=invalidation_conditions,
    )


def build_break_monitor(asset: Asset, prices: List[PricePoint], news_items: List[NewsItem]) -> BreakMonitorResponse:
    closes = [p.close for p in prices]
    last_close = closes[-1]
    ema20 = ema(closes, 20)[-1] if len(closes) >= 20 else last_close
    sentiment = compute_sentiment_score(news_items)
    shift = compute_narrative_shift_score(news_items)

    def status_for_distance(current: float, threshold: float, inverse: bool = False) -> str:
        if inverse:
            if current <= threshold:
                return "red"
            if current <= threshold * 1.03:
                return "yellow"
            return "green"
        if current >= threshold:
            return "red"
        if current >= threshold * 0.85:
            return "yellow"
        return "green"

    items = [
        BreakMonitorItem(
            condition="Cena poniżej EMA20",
            current_value=f"close={last_close:.2f}, ema20={ema20:.2f}",
            status=status_for_distance(last_close, ema20, inverse=True),
            severity="high",
        ),
        BreakMonitorItem(
            condition="Sentyment spada poniżej 0",
            current_value=f"sentiment={sentiment:.2f}",
            status="red" if sentiment < 0 else "yellow" if sentiment < 10 else "green",
            severity="medium",
        ),
        BreakMonitorItem(
            condition="Silna zmiana narracji > 40",
            current_value=f"narrative_shift={shift:.2f}",
            status=status_for_distance(shift, 40),
            severity="medium",
        ),
    ]
    return BreakMonitorResponse(asset_id=asset.id, generated_at=utc_now(), items=items)
