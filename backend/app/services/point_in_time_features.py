"""Point-in-time enrichment for the ML dataset.

Every feature in this module is built only from information that was available
at ``snapshot_at``.  In particular, insider transactions use the filing date
(not the transaction date), short-interest snapshots use their ingestion time,
and news use the exact publication timestamp.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    EarningsORM, InsiderTradeORM, NewsItemORM, NewsNLPRunORM, ShortInterestORM,
)
from app.utils.datetime import ensure_utc


FEATURE_GROUPS: dict[str, list[str]] = {
    "availability": ["has_iv", "has_upcoming_earnings"],
    "earnings": [
        "has_earnings", "days_since_earnings", "eps_surprise_pct",
        "revenue_surprise_pct", "has_pead_1d", "pead_return_1d_pct",
        "has_pead_5d", "pead_return_5d_pct",
    ],
    "insider_short": [
        "has_insider_90d", "insider_net_value_log_90d",
        "insider_buy_ratio_90d", "insider_cluster_buyers_90d",
        "days_since_insider_filing", "has_short_interest",
        "short_percent_float", "short_ratio", "short_percent_change",
    ],
    "event_news": [
        "news_event_positive_7d", "news_event_negative_7d",
        "news_event_earnings_guidance_7d", "news_event_corporate_action_7d",
        "news_event_financing_7d", "news_event_legal_regulatory_7d",
        "news_event_contract_product_7d", "news_event_management_cyber_7d",
        "news_attention_zscore_7d", "news_source_diversity_7d",
        "news_high_impact_7d", "news_nlp_coverage_7d",
        "news_relevance_mean_7d", "news_sentiment_confidence_mean_7d",
    ],
}


_EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "earnings_guidance": (
        "earnings", "results", "revenue", "profit", "eps", "guidance",
        "outlook", "forecast", "wyniki", "przychod", "zysk", "prognoz",
    ),
    "corporate_action": (
        "acquisition", "merger", "takeover", "buyback", "dividend", "split",
        "przej", "fuzj", "skup akcji", "dywidend", "podział akcji",
    ),
    "financing": (
        "offering", "dilution", "debt", "bond", "refinanc", "liquidity",
        "emisj", "zadłuż", "obligac", "płynnoś",
    ),
    "legal_regulatory": (
        "lawsuit", "court", "probe", "investigation", "regulator", "antitrust",
        "sec ", "fda ", "pozew", "sąd", "śledztw", "regulator", "uokik", "knf ",
    ),
    "contract_product": (
        "contract", "order", "partnership", "launch", "approval", "product",
        "kontrakt", "zamówien", "partnerstw", "premier", "produkt", "zatwierdz",
    ),
    "management_cyber": (
        "ceo", "cfo", "management", "resign", "appoint", "cyber", "breach",
        "hack", "zarząd", "prezes", "rezygn", "powoł", "atak", "wyciek danych",
    ),
}


def classify_news_events(title: str, body: str = "") -> set[str]:
    """Small deterministic taxonomy; stable enough for historical backfills."""
    text = f" {title} {body} ".lower()
    return {
        label for label, keywords in _EVENT_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


def _date_of(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    return value


def _signed_log(value: float) -> float:
    return math.copysign(math.log1p(abs(value)), value) if value else 0.0


class PointInTimeFeatureStore:
    """Preloaded per-asset data store used by both training and live scoring."""

    def __init__(self, db: Session, asset_id: str):
        self.earnings = list(db.scalars(
            select(EarningsORM).where(EarningsORM.asset_id == asset_id)
            .order_by(EarningsORM.report_date.asc())
        ).all())
        self.insiders = list(db.scalars(
            select(InsiderTradeORM).where(InsiderTradeORM.asset_id == asset_id)
            .order_by(InsiderTradeORM.transaction_date.asc())
        ).all())
        self.short_interest = list(db.scalars(
            select(ShortInterestORM).where(ShortInterestORM.asset_id == asset_id)
            .order_by(ShortInterestORM.report_date.asc())
        ).all())
        self.news = list(db.scalars(
            select(NewsItemORM).where(NewsItemORM.asset_id == asset_id)
            .order_by(NewsItemORM.published_at.asc())
        ).all())
        self.news_times = [ensure_utc(row.published_at) for row in self.news]
        nlp_by_news: dict[str, list[NewsNLPRunORM]] = defaultdict(list)
        for run in db.scalars(
            select(NewsNLPRunORM)
            .join(NewsItemORM, NewsItemORM.id == NewsNLPRunORM.news_id)
            .where(NewsItemORM.asset_id == asset_id)
            .order_by(NewsNLPRunORM.processed_at.asc())
        ).all():
            nlp_by_news[run.news_id].append(run)
        self.nlp_by_news = dict(nlp_by_news)

    def _known_nlp_run(self, news_id: str, snapshot_at: datetime) -> NewsNLPRunORM | None:
        runs = self.nlp_by_news.get(news_id, [])
        known = [run for run in runs if ensure_utc(run.processed_at) <= snapshot_at]
        return known[-1] if known else None

    @staticmethod
    def _earnings_available_on(row: EarningsORM) -> date:
        # Without an exact publication time, never expose the result on the
        # report date itself.  created_at prevents retroactive provider imports.
        return max(row.report_date + timedelta(days=1), _date_of(row.created_at) or row.report_date)

    @staticmethod
    def _insider_available_on(row: InsiderTradeORM) -> date:
        filing = row.filing_date or _date_of(row.created_at) or row.transaction_date
        return max(filing + timedelta(days=1), _date_of(row.created_at) or filing)

    @staticmethod
    def _short_available_on(row: ShortInterestORM) -> date:
        created = _date_of(row.created_at) or row.report_date
        return max(row.report_date + timedelta(days=1), created + timedelta(days=1))

    @staticmethod
    def _pead_return(
        available_on: date, sessions: int, snapshot_date: date,
        price_dates: list[date], closes: list[float],
    ) -> float | None:
        start = next((i for i, day in enumerate(price_dates) if day >= available_on), None)
        if start is None or start + sessions >= len(price_dates):
            return None
        if price_dates[start + sessions] > snapshot_date or not closes[start]:
            return None
        return (closes[start + sessions] - closes[start]) / closes[start] * 100.0

    def build(
        self, snapshot_at: datetime, *, has_iv: bool,
        price_dates: list[date] | None = None, closes: list[float] | None = None,
    ) -> dict[str, float]:
        snap_dt = ensure_utc(snapshot_at)
        snap_date = snap_dt.date()
        price_dates = price_dates or []
        closes = closes or []

        # Earnings are usable only after their conservative availability date.
        known_earnings = [
            row for row in self.earnings
            if not row.is_upcoming and self._earnings_available_on(row) <= snap_date
            and (row.eps_actual is not None or row.revenue_actual is not None)
        ]
        latest_earnings = known_earnings[-1] if known_earnings else None
        earnings_available = self._earnings_available_on(latest_earnings) if latest_earnings else None
        revenue_surprise = None
        if latest_earnings and latest_earnings.revenue_actual is not None and latest_earnings.revenue_estimate not in (None, 0):
            revenue_surprise = (
                (latest_earnings.revenue_actual - latest_earnings.revenue_estimate)
                / abs(latest_earnings.revenue_estimate) * 100.0
            )
        pead_1d = self._pead_return(earnings_available, 1, snap_date, price_dates, closes) if earnings_available else None
        pead_5d = self._pead_return(earnings_available, 5, snap_date, price_dates, closes) if earnings_available else None

        upcoming = [
            row for row in self.earnings
            if row.is_upcoming and row.report_date >= snap_date
            and (_date_of(row.created_at) or date.max) <= snap_date
        ]
        next_earnings = min((row.report_date for row in upcoming), default=None)

        # Filing date is the public-information boundary for insiders.
        insider_cutoff = snap_date - timedelta(days=90)
        known_insiders = [
            row for row in self.insiders
            if insider_cutoff <= self._insider_available_on(row) <= snap_date
            and row.transaction_type in {"buy", "sell"}
        ]
        buy_value = sum(abs(row.value or 0.0) for row in known_insiders if row.transaction_type == "buy")
        sell_value = sum(abs(row.value or 0.0) for row in known_insiders if row.transaction_type == "sell")
        gross_value = buy_value + sell_value
        net_value = buy_value - sell_value
        buyers = {row.name for row in known_insiders if row.transaction_type == "buy"}
        last_filing = max((self._insider_available_on(row) for row in known_insiders), default=None)

        known_short = [row for row in self.short_interest if self._short_available_on(row) <= snap_date]
        latest_short = known_short[-1] if known_short else None
        previous_short = known_short[-2] if len(known_short) >= 2 else None
        short_change = None
        if latest_short and previous_short and latest_short.short_percent_float is not None and previous_short.short_percent_float not in (None, 0):
            short_change = (
                (latest_short.short_percent_float - previous_short.short_percent_float)
                / abs(previous_short.short_percent_float) * 100.0
            )

        recent_cutoff = snap_dt - timedelta(days=7)
        baseline_cutoff = snap_dt - timedelta(days=91)
        end_index = bisect_right(self.news_times, snap_dt)
        recent_index = bisect_right(self.news_times, recent_cutoff, hi=end_index)
        baseline_index = bisect_right(self.news_times, baseline_cutoff, hi=recent_index)
        recent_news = self.news[recent_index:end_index]
        baseline_news = self.news[baseline_index:recent_index]
        recent_pairs = [
            (row, self._known_nlp_run(row.id, snap_dt)) for row in recent_news
        ]
        eligible_pairs = [
            (row, run) for row, run in recent_pairs
            if run is not None and float(run.relevance_score) >= settings.news_min_relevance
        ]
        eligible_baseline = [
            row for row in baseline_news
            if (run := self._known_nlp_run(row.id, snap_dt)) is not None
            and float(run.relevance_score) >= settings.news_min_relevance
        ]
        event_counts: Counter[str] = Counter()
        positive = negative = high_impact = 0.0
        nlp_count = 0
        relevance_sum = confidence_sum = 0.0
        for row, nlp in eligible_pairs:
            sentiment = float(nlp.sentiment_score)
            relevance = float(nlp.relevance_score)
            confidence = float(nlp.sentiment_confidence)
            nlp_count += 1
            relevance_sum += relevance
            confidence_sum += confidence
            events = classify_news_events(row.title, row.body)
            if not events:
                continue
            for event in events:
                event_counts[event] += 1
            weight = abs(float(row.impact_score or 0.0)) * relevance * confidence
            if sentiment > 0.1:
                positive += weight
            elif sentiment < -0.1:
                negative += weight
            if float(row.impact_score or 0.0) >= 0.65:
                high_impact += 1.0
        weekly_baseline = len(eligible_baseline) / 12.0
        attention_z = (len(eligible_pairs) - weekly_baseline) / math.sqrt(weekly_baseline + 1.0)

        return {
            "has_iv": float(has_iv),
            "has_upcoming_earnings": float(bool(upcoming)),
            "days_to_earnings": float(min((next_earnings - snap_date).days, 90)) if next_earnings else 90.0,
            "has_earnings": float(latest_earnings is not None),
            "days_since_earnings": float(min((snap_date - earnings_available).days, 365)) if earnings_available else 365.0,
            "eps_surprise_pct": float(latest_earnings.eps_surprise_pct or 0.0) if latest_earnings else 0.0,
            "revenue_surprise_pct": float(revenue_surprise or 0.0),
            "has_pead_1d": float(pead_1d is not None),
            "pead_return_1d_pct": float(pead_1d or 0.0),
            "has_pead_5d": float(pead_5d is not None),
            "pead_return_5d_pct": float(pead_5d or 0.0),
            "has_insider_90d": float(bool(known_insiders)),
            "insider_net_value_log_90d": _signed_log(net_value),
            "insider_buy_ratio_90d": buy_value / gross_value if gross_value else 0.0,
            "insider_cluster_buyers_90d": float(min(len(buyers), 10)),
            "days_since_insider_filing": float(min((snap_date - last_filing).days, 365)) if last_filing else 365.0,
            "has_short_interest": float(latest_short is not None),
            "short_percent_float": float(latest_short.short_percent_float or 0.0) if latest_short else 0.0,
            "short_ratio": float(latest_short.short_ratio or 0.0) if latest_short else 0.0,
            "short_percent_change": float(short_change or 0.0),
            "news_event_positive_7d": round(positive, 6),
            "news_event_negative_7d": round(negative, 6),
            "news_event_earnings_guidance_7d": float(event_counts["earnings_guidance"]),
            "news_event_corporate_action_7d": float(event_counts["corporate_action"]),
            "news_event_financing_7d": float(event_counts["financing"]),
            "news_event_legal_regulatory_7d": float(event_counts["legal_regulatory"]),
            "news_event_contract_product_7d": float(event_counts["contract_product"]),
            "news_event_management_cyber_7d": float(event_counts["management_cyber"]),
            "news_attention_zscore_7d": round(attention_z, 6),
            "news_source_diversity_7d": float(len({row.source for row, _ in eligible_pairs})),
            "news_high_impact_7d": high_impact,
            "news_nlp_coverage_7d": sum(run is not None for _, run in recent_pairs) / len(recent_news) if recent_news else 0.0,
            "news_relevance_mean_7d": relevance_sum / nlp_count if nlp_count else 0.0,
            "news_sentiment_confidence_mean_7d": confidence_sum / nlp_count if nlp_count else 0.0,
            # Replace the historically incorrect now()-based count in old snapshots.
            "news_count_7d": float(len(eligible_pairs)),
        }
