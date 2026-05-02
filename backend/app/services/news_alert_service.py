"""
news_alert_service.py — monitoring newsow w czasie rzeczywistym via Finnhub.

Odpytuje Finnhub company-news co 5 minut dla aktywow z portfela i watchlist.
Wysluje SMS gdy pojawi sie wazny negatywny news zanim rynek zareaguje.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import httpx

from app.core.config import settings

# ── Deduplicja: juz przetworzone news ID (in-memory, reset przy restarcie) ───
_seen_news_ids: set[str] = set()

# ── Slowa kluczowe: negatywne ────────────────────────────────────────────────
_NEG_KEYWORDS: list[str] = [
    # Wyniki finansowe
    "miss", "misses", "missed", "below expectations", "below estimates",
    "below consensus", "revenue miss", "earnings miss", "eps miss",
    "revenue fell", "revenue declined", "revenue dropped", "net loss",
    "worse than expected", "disappoint", "disappoints", "disappointed",
    "weak results", "weaker than expected", "shortfall",
    # Guidance
    "cuts guidance", "lowers guidance", "reduces guidance", "guidance cut",
    "below guidance", "withdraws guidance", "suspends guidance",
    "guidance withdrawn", "pulls guidance", "slashes guidance",
    # Cecia i redukcje
    "layoffs", "layoff", "job cuts", "job cut", "workforce reduction",
    "restructuring charge", "write-down", "writedown", "impairment",
    "one-time charge", "goodwill impairment", "asset impairment",
    # Regulacje i prawne
    "lawsuit", "sec investigation", "doj investigation", "antitrust",
    "fine", "penalty", "regulatory action", "investigation", "probe",
    "subpoena", "class action", "securities fraud",
    # Makro
    "tariff", "tariffs", "trade war", "sanctions", "export ban",
    "export restriction", "ban on", "blocked",
    # Zarzad
    "ceo resign", "cfo resign", "ceo fired", "coo resign",
    "ceo leaves", "cfo leaves", "leadership change", "abrupt departure",
    # Ratingi i rekomendacje
    "downgrade", "downgraded", "cut to sell", "price target cut",
    "underperform", "underweight", "sell rating", "target lowered",
    # Powazne
    "bankruptcy", "chapter 11", "default", "debt restructuring",
    "trading halted", "suspended trading", "going concern",
    # Makro i sektor
    "recession fears", "slowdown", "demand weakness", "inventory buildup",
    "margin compression", "margin pressure", "cost overruns",
]

# ── Slowa kluczowe: pozytywne (zmniejszaja score) ────────────────────────────
_POS_KEYWORDS: list[str] = [
    "beats", "beat", "exceeds", "exceeded", "above expectations",
    "above estimates", "above consensus", "record revenue", "record earnings",
    "record profit", "raises guidance", "increases guidance", "raises outlook",
    "upgrade", "upgraded", "outperform", "overweight", "buy rating",
    "price target raised", "strong results", "better than expected",
    "record quarter", "record year",
]


class NewsSignal(NamedTuple):
    asset_id: str
    symbol: str
    headline: str
    source: str
    published_at: datetime
    neg_score: int
    pos_score: int
    news_id: str


def _score(headline: str, body: str) -> tuple[int, int]:
    text = f"{headline} {body}".lower()
    neg = sum(1 for kw in _NEG_KEYWORDS if kw in text)
    pos = sum(1 for kw in _POS_KEYWORDS if kw in text)
    return neg, pos


def scan_recent_news(
    assets: list[tuple[str, str, str | None]],  # (asset_id, symbol, news_symbol)
    lookback_minutes: int = 90,
) -> list[NewsSignal]:
    """
    Pobiera newsy z Finnhub dla podanych aktywow z ostatnich lookback_minutes minut.
    Zwraca posortowana liste negatywnych sygnalow (bez duplikatow).
    assets: lista (asset_id, symbol, news_symbol)
    """
    if not settings.finnhub_api_key or not assets:
        return []

    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(minutes=lookback_minutes)).date().isoformat()
    date_to = now.date().isoformat()
    cutoff = now - timedelta(minutes=lookback_minutes)

    signals: list[NewsSignal] = []

    with httpx.Client(timeout=12) as client:
        for idx, (asset_id, symbol, news_symbol) in enumerate(assets):
            fh_sym = (news_symbol or symbol or "").upper()
            if not fh_sym:
                continue
            # Niewielki throttle zeby nie trafia w rate limit Finnhub (60 req/min)
            if idx > 0:
                time.sleep(0.5)
            try:
                resp = client.get(
                    "https://finnhub.io/api/v1/company-news",
                    params={
                        "symbol": fh_sym,
                        "from": date_from,
                        "to": date_to,
                        "token": settings.finnhub_api_key,
                    },
                )
                resp.raise_for_status()
                items = resp.json()
                if not isinstance(items, list):
                    continue

                for item in items:
                    pub_ts = item.get("datetime", 0)
                    if not pub_ts:
                        continue
                    pub_dt = datetime.fromtimestamp(int(pub_ts), tz=timezone.utc)
                    if pub_dt < cutoff:
                        continue

                    headline = item.get("headline", "") or ""
                    body = item.get("summary", "") or ""
                    news_id = f"na-{asset_id}-{item.get('id') or pub_ts}"

                    if news_id in _seen_news_ids:
                        continue

                    neg, pos = _score(headline, body)

                    # Alert gdy: jest negatywny sygnał i dominuje nad pozytywnym
                    # LUB jest bardzo silny negatywny (>=3) nawet przy pozytywnym
                    if neg >= 1 and (neg > pos or neg >= 3):
                        signals.append(NewsSignal(
                            asset_id=asset_id,
                            symbol=symbol,
                            headline=headline[:200],
                            source=item.get("source", "Finnhub"),
                            published_at=pub_dt,
                            neg_score=neg,
                            pos_score=pos,
                            news_id=news_id,
                        ))

            except Exception as exc:
                print(f"[news-alert] blad fetch {fh_sym}: {exc}")

    signals.sort(key=lambda s: (s.neg_score, s.published_at), reverse=True)
    return signals


def mark_seen(news_ids: list[str]) -> None:
    _seen_news_ids.update(news_ids)
    # Ogranicz rozmiar setu (max 10 000 ID)
    if len(_seen_news_ids) > 10_000:
        to_remove = list(_seen_news_ids)[:2_000]
        for nid in to_remove:
            _seen_news_ids.discard(nid)