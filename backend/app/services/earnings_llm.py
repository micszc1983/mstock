"""
earnings_llm.py

Analiza wyników kwartalnych przy pomocy Claude (Anthropic API).

Schemat:
  1. Pobierz artykuły newsowe z ±2 dni wokół daty raportu (z bazy NewsItemORM).
  2. Zbuduj prompt z danymi EPS + kontekstem newsowym.
  3. Wyślij do claude-haiku — szybkiego i taniego modelu do analizy.
  4. Sparsuj odpowiedź JSON i zapisz do EarningsCallAnalysisORM.

Nie wymaga dostępu do transkryptów (Finnhub premium). Działa na newsach
z bazy MStock dla US stocks. GPW/metale są automatycznie pomijane
gdy nie mają zebranych newsów w bazie.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AssetORM, EarningsCallAnalysisORM, EarningsORM, NewsItemORM
from app.repositories.earnings_analysis import upsert_earnings_analysis


_MODEL = "claude-haiku-4-5-20251001"
_MAX_NEWS = 8
_MAX_BODY_CHARS = 600


def _get_news_around_date(db: Session, asset_id: str, report_date, days: int = 2) -> list[NewsItemORM]:
    from datetime import date
    if isinstance(report_date, date) and not isinstance(report_date, datetime):
        start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc) - timedelta(days=days)
        end   = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc) + timedelta(days=days + 1)
    else:
        start = report_date - timedelta(days=days)
        end   = report_date + timedelta(days=days + 1)

    stmt = (
        select(NewsItemORM)
        .where(
            NewsItemORM.asset_id == asset_id,
            NewsItemORM.published_at >= start,
            NewsItemORM.published_at <= end,
        )
        .order_by(NewsItemORM.published_at.desc())
        .limit(_MAX_NEWS)
    )
    return db.scalars(stmt).all()


def _build_prompt(asset: AssetORM, earnings: EarningsORM, news_items: list[NewsItemORM]) -> str:
    eps_line = "EPS data: not available"
    if earnings.eps_estimate is not None and earnings.eps_actual is not None:
        eps_line = (
            f"EPS estimate: {earnings.eps_estimate:.2f}, "
            f"EPS actual: {earnings.eps_actual:.2f}, "
            f"Surprise: {earnings.eps_surprise_pct:+.1f}% ({earnings.surprise_label})"
        )
    elif earnings.eps_actual is not None:
        eps_line = f"EPS actual: {earnings.eps_actual:.2f} (no estimate)"

    if news_items:
        parts = ["\n\nNews articles from around the earnings date:"]
        for i, item in enumerate(news_items, 1):
            body_snippet = ""
            if item.body and len(item.body) > 50:
                body_snippet = item.body[:_MAX_BODY_CHARS]
                if len(item.body) > _MAX_BODY_CHARS:
                    body_snippet += "..."
            parts.append(
                f"\n[{i}] {item.published_at.strftime('%Y-%m-%d')} — {item.source}\n"
                f"Headline: {item.title}\n"
                + (f"Content: {body_snippet}\n" if body_snippet else "")
            )
        news_block = "".join(parts)
    else:
        news_block = "\n\nNo news articles found for this earnings period."

    return f"""You are a financial analyst specializing in earnings analysis.
Analyze the following quarterly earnings information for {asset.name} ({asset.symbol}).

Earnings Report:
- Date: {earnings.report_date}
- Period: {earnings.fiscal_period or "N/A"}
- {eps_line}
{news_block}

Based on the available information, respond with ONLY a valid JSON object (no markdown, no extra text):
{{
  "tone_score": <integer 1-5; 1=very bearish management tone, 3=neutral, 5=very bullish>,
  "guidance_change": <"raised" | "lowered" | "maintained" | "none">,
  "key_themes": <list of 3-5 key themes in Polish, e.g. ["Wzrost przychodów", "Marże pod presją"]>,
  "risk_factors": <list of 2-4 risk factors in Polish>,
  "key_quote": <single most important insight in Polish, max 200 characters or null>,
  "llm_sentiment_score": <float -100.0 to 100.0; negative=bearish, positive=bullish>,
  "summary": <2-3 sentences in Polish for an investor, focus on what changed and why it matters>
}}"""


def analyze_earnings(
    db: Session, earnings: EarningsORM, asset: AssetORM
) -> Optional[EarningsCallAnalysisORM]:
    """
    Przeprowadza analizę LLM dla jednego rekordu wynikowego.
    Zwraca zapisany obiekt analizy lub None gdy brak klucza / błąd.
    """
    if not settings.anthropic_api_key:
        print("[earnings_llm] Brak ANTHROPIC_API_KEY — analiza LLM pominięta")
        return None

    try:
        import anthropic
    except ImportError:
        print("[earnings_llm] Brak pakietu 'anthropic' — zainstaluj: pip install anthropic")
        return None

    news_items = _get_news_around_date(db, earnings.asset_id, earnings.report_date, days=2)
    prompt = _build_prompt(asset, earnings, news_items)

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_response = message.content[0].text.strip()
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        print(f"[earnings_llm] Nieprawidłowy JSON od Claude: {exc}")
        return None
    except Exception as exc:
        print(f"[earnings_llm] Błąd Claude API dla {asset.id}: {exc}")
        return None

    try:
        analysis = upsert_earnings_analysis(
            db=db,
            earnings_id=earnings.id,
            asset_id=earnings.asset_id,
            tone_score=max(1, min(5, int(data.get("tone_score", 3)))),
            guidance_change=data.get("guidance_change", "none"),
            key_themes_json=json.dumps(data.get("key_themes", []), ensure_ascii=False),
            risk_factors_json=json.dumps(data.get("risk_factors", []), ensure_ascii=False),
            key_quote=data.get("key_quote"),
            llm_sentiment_score=float(data.get("llm_sentiment_score", 0.0)),
            summary=data.get("summary", ""),
            model_used=_MODEL,
            news_articles_used=len(news_items),
            raw_response=raw_response,
        )
        db.commit()
        print(f"[earnings_llm] Analiza zapisana: {asset.id} / {earnings.report_date} (news: {len(news_items)})")
        return analysis
    except Exception as exc:
        print(f"[earnings_llm] Błąd zapisu analizy: {exc}")
        db.rollback()
        return None


def analyze_latest_earnings_for_asset(db: Session, asset_id: str) -> Optional[EarningsCallAnalysisORM]:
    """Analizuje najnowszy *historyczny* rekord wynikowy dla aktywa (jeśli nie był jeszcze analizowany)."""
    from app.repositories.earnings import get_latest_earnings
    from app.repositories.earnings_analysis import get_analysis_for_earnings
    from app.repositories.assets import get_asset

    earnings = get_latest_earnings(db, asset_id)
    if earnings is None:
        return None

    existing = get_analysis_for_earnings(db, earnings.id)
    if existing is not None:
        return existing  # już przeanalizowane

    asset = get_asset(db, asset_id)
    if asset is None:
        return None

    return analyze_earnings(db, earnings, asset)


def analyze_all_pending(db: Session) -> dict[str, int]:
    """
    Analizuje najnowsze wyniki dla wszystkich aktywów które jeszcze nie mają analizy LLM.
    Zwraca {asset_id: 1} dla przeanalizowanych.
    """
    from app.repositories.assets import list_assets
    results: dict[str, int] = {}
    for asset in list_assets(db):
        if asset.type == "metal":
            continue
        try:
            result = analyze_latest_earnings_for_asset(db, asset.id)
            if result is not None:
                results[asset.id] = 1
        except Exception as exc:
            print(f"[earnings_llm] {asset.id}: błąd — {exc}")
    return results
