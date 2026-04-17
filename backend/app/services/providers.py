from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.asset import PricePoint
from app.schemas.common import AssetType, NarrativeLabel
from app.schemas.news import NewsItem


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def require_api_key(api_key: str, env_name: str) -> None:
    if not api_key:
        raise HTTPException(status_code=400, detail=f"Missing {env_name}. Set it in environment variables.")


# UWAGA: Kanoniczna implementacja przeniesiona do app/services/nlp_backends/heuristic.py
# Ta funkcja pozostaje dla kompatybilności wstecznej przy pobieraniu newsów.
def infer_sentiment_from_text(title: str, body: str) -> float:
    text = f"{title} {body}".lower()
    positive = ["strong", "beats", "support", "growth", "record", "upgrades", "improves", "bullish"]
    negative = ["risk", "miss", "cut", "pressure", "decline", "lawsuit", "weak", "bearish"]
    pos_hits = sum(1 for word in positive if word in text)
    neg_hits = sum(1 for word in negative if word in text)
    return clamp((pos_hits - neg_hits) / 4.0, -1.0, 1.0)


def infer_impact_from_text(title: str, body: str) -> float:
    text = f"{title} {body}".lower()
    high_impact_terms = ["earnings", "guidance", "lawsuit", "fed", "tariff", "export", "acquisition", "central bank"]
    hits = sum(1 for word in high_impact_terms if word in text)
    return clamp(0.45 + hits * 0.12, 0.35, 0.95)


def infer_narratives_from_text(title: str, body: str, asset_type: AssetType) -> Dict[NarrativeLabel, float]:
    text = f"{title} {body}".lower()
    scores: Dict[NarrativeLabel, float] = {}

    def hit(label: NarrativeLabel, keywords: List[str], score: float = 0.75) -> None:
        if any(keyword in text for keyword in keywords):
            scores[label] = max(scores.get(label, 0.0), score)

    if asset_type == AssetType.STOCK:
        hit(NarrativeLabel.AI_GROWTH, ["ai", "artificial intelligence", "data center", "gpu"])
        hit(NarrativeLabel.MARGIN_PRESSURE, ["margin", "cost pressure", "pricing pressure"])
        hit(NarrativeLabel.DEMAND_STRENGTH, ["demand", "orders", "growth", "capex"])
        hit(NarrativeLabel.DEMAND_SLOWDOWN, ["slowdown", "weak demand", "soft demand"])
        hit(NarrativeLabel.REGULATION_RISK, ["regulation", "antitrust", "export restriction", "lawsuit"])
        hit(NarrativeLabel.VALUATION_STRETCH, ["valuation", "overvalued", "multiple expansion"])
    else:
        hit(NarrativeLabel.SAFE_HAVEN, ["safe haven", "geopolitical", "flight to safety", "uncertainty"])
        hit(NarrativeLabel.RATES_PRESSURE, ["rates", "yield", "real yield", "fed"])
        hit(NarrativeLabel.DOLLAR_PRESSURE, ["dollar", "usd"])
        hit(NarrativeLabel.CENTRAL_BANK_BUYING, ["central bank", "reserve diversification"])
        hit(NarrativeLabel.INDUSTRIAL_DEMAND, ["industrial demand", "manufacturing", "electronics", "automotive"])
        hit(NarrativeLabel.SUPPLY_DISRUPTION, ["mine", "supply disruption", "production cut", "sanction"])

    if not scores:
        default_label = NarrativeLabel.DEMAND_STRENGTH if asset_type == AssetType.STOCK else NarrativeLabel.SAFE_HAVEN
        scores[default_label] = 0.3
    return scores




def fetch_search_news_from_finnhub(term: str, asset_id: str, asset_type: AssetType) -> List[NewsItem]:
    """
    Pobiera general market news z Finnhub i filtruje po term.
    Używane dla spółek spoza US (np. KGHM, PKN, CCC) gdzie company-news endpoint
    nie działa (GPW nie jest wspierana przez Finnhub).
    """
    require_api_key(settings.finnhub_api_key, "FINNHUB_API_KEY")
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": settings.finnhub_api_key}
    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, list):
        return []

    term_l = term.lower()
    items: List[NewsItem] = []
    for article in data:
        headline = (article.get("headline") or "").lower()
        summary  = (article.get("summary") or "").lower()
        if term_l not in headline and term_l not in summary:
            continue
        pub_ts = article.get("datetime", 0)
        pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc) if pub_ts else datetime.now(timezone.utc)
        identifier = article.get("id") or article.get("url") or f"{asset_id}-{pub_ts}"
        items.append(NewsItem(
            id=f"finnhub-general-{asset_id}-{identifier}",
            asset_id=asset_id,
            source="finnhub:general",
            title=article.get("headline", ""),
            body=article.get("summary", ""),
            url=article.get("url", ""),
            published_at=pub_dt,
            sentiment_score=0.0,
            impact_score=0.5,
        ))
    return items

def fetch_quote_from_finnhub(symbol: str) -> List[PricePoint]:
    """
    Pobiera aktualny kurs z Finnhub /quote.
    Używane jako ostatni fallback gdy Alpaca i Alpha Vantage są niedostępne.
    Zwraca 1 punkt danych (dzisiejszy OHLCV).
    Działa tylko dla US stocks na darmowym planie Finnhub.
    """
    require_api_key(settings.finnhub_api_key, "FINNHUB_API_KEY")
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": settings.finnhub_api_key}
    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    close = data.get("c", 0)
    if not close or close == 0:
        return []  # Brak danych (symbol nieobsługiwany lub rynek zamknięty bez ceny)

    ts_unix = data.get("t", 0)
    ts = datetime.fromtimestamp(ts_unix, tz=timezone.utc) if ts_unix else datetime.now(timezone.utc)

    return [PricePoint(
        timestamp=ts,
        open=float(data.get("o") or close),
        high=float(data.get("h") or close),
        low=float(data.get("l") or close),
        close=float(close),
        volume=0.0,
    )]


def fetch_stock_prices_from_alpha_vantage(symbol: str) -> List[PricePoint]:
    require_api_key(settings.alphavantage_api_key, "ALPHAVANTAGE_API_KEY")
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
        "apikey": settings.alphavantage_api_key,
    }
    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict):
        detail = payload.get("Note") or payload.get("Information") or payload.get("Error Message") or "Unexpected Alpha Vantage response"
        raise HTTPException(status_code=502, detail=f"Alpha Vantage price sync failed: {detail}")

    points: List[PricePoint] = []
    for day, values in sorted(series.items()):
        points.append(
            PricePoint(
                timestamp=datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
                open=float(values["1. open"]),
                high=float(values["2. high"]),
                low=float(values["3. low"]),
                close=float(values["4. close"]),
                volume=float(values["5. volume"]),
            )
        )
    return points


def fetch_metal_prices_from_alpha_vantage(function_name: str) -> List[PricePoint]:
    require_api_key(settings.alphavantage_api_key, "ALPHAVANTAGE_API_KEY")
    url = "https://www.alphavantage.co/query"
    params = {"function": function_name, "interval": "daily", "apikey": settings.alphavantage_api_key}
    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data")
    if not isinstance(data, list):
        detail = payload.get("Note") or payload.get("Error Message") or "Unexpected Alpha Vantage metal response"
        raise HTTPException(status_code=502, detail=f"Alpha Vantage metal sync failed: {detail}")

    points: List[PricePoint] = []
    for row in reversed(data):
        close = float(row["value"])
        ts = datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc)
        points.append(PricePoint(timestamp=ts, open=close, high=close, low=close, close=close, volume=0.0))
    return points


def fetch_company_news_from_finnhub(symbol: str, asset_id: str, asset_type: AssetType) -> List[NewsItem]:
    require_api_key(settings.finnhub_api_key, "FINNHUB_API_KEY")
    now_utc = datetime.now(timezone.utc)
    date_from = (now_utc - timedelta(days=30)).date().isoformat()
    date_to = now_utc.date().isoformat()

    url = "https://finnhub.io/api/v1/company-news"
    params = {"symbol": symbol, "from": date_from, "to": date_to, "token": settings.finnhub_api_key}

    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        raise HTTPException(status_code=502, detail="Finnhub news sync failed: unexpected response")

    items: List[NewsItem] = []
    for entry in payload[:50]:
        title = entry.get("headline", "")
        body = entry.get("summary", "")
        identifier = str(entry.get("id") or entry.get("datetime") or title[:50])
        published_at = datetime.fromtimestamp(int(entry.get("datetime", 0)), tz=timezone.utc)
        items.append(
            NewsItem(
                id=f"finnhub-{asset_id}-{identifier}",
                asset_id=asset_id,
                published_at=published_at,
                source=str(entry.get("source") or "Finnhub"),
                title=title,
                body=body,
                sentiment_score=infer_sentiment_from_text(title, body),
                impact_score=infer_impact_from_text(title, body),
                narratives=infer_narratives_from_text(title, body, asset_type),
            )
        )
    return items


def fetch_search_news_from_alpha_vantage(term: str, asset_id: str, asset_type: AssetType) -> List[NewsItem]:
    require_api_key(settings.alphavantage_api_key, "ALPHAVANTAGE_API_KEY")
    url = "https://www.alphavantage.co/query"
    params = {"function": "NEWS_SENTIMENT", "keywords": term, "limit": 50, "apikey": settings.alphavantage_api_key}
    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    feed = payload.get("feed")
    if not isinstance(feed, list):
        detail = payload.get("Note") or payload.get("Error Message") or "Unexpected Alpha Vantage news response"
        raise HTTPException(status_code=502, detail=f"Alpha Vantage news sync failed: {detail}")

    items: List[NewsItem] = []
    for entry in feed[:50]:
        title = str(entry.get("title") or "")
        body = str(entry.get("summary") or "")
        published_at = datetime.strptime(str(entry.get("time_published")), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        overall_sentiment = entry.get("overall_sentiment_score")
        sentiment_score = clamp(float(overall_sentiment), -1.0, 1.0) if overall_sentiment is not None else infer_sentiment_from_text(title, body)
        items.append(
            NewsItem(
                id=f"av-news-{asset_id}-{hash(str(entry.get('url', title)))}",
                asset_id=asset_id,
                published_at=published_at,
                source=str(entry.get("source") or "AlphaVantage"),
                title=title,
                body=body,
                sentiment_score=sentiment_score,
                impact_score=infer_impact_from_text(title, body),
                narratives=infer_narratives_from_text(title, body, asset_type),
            )
        )
    return items

# ══════════════════════════════════════════════════════════════════
#  Alpaca Markets — ceny dzienne i newsy
#  Dokumentacja: https://docs.alpaca.markets/docs/about-market-data-api
#  Auth: nagłówki APCA-API-KEY-ID + APCA-API-SECRET-KEY
#  Limit: 10 000 req/min (plan darmowy: dane z 15-minutowym opóźnieniem)
#  Rejestracja: https://alpaca.markets/
# ══════════════════════════════════════════════════════════════════

_ALPACA_DATA_BASE = "https://data.alpaca.markets/v2"


def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        "Accept":              "application/json",
    }


def fetch_stock_prices_from_alpaca(symbol: str) -> List[PricePoint]:
    """
    Pobiera dzienne bary OHLCV z Alpaca dla podanego tickera (US stocks).
    Endpoint: GET /v2/stocks/{symbol}/bars
    Parametry: timeframe=1Day, limit=100, feed=iex (darmowy plan)
    Zwraca listę PricePoint posortowaną rosnąco po dacie.
    """
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        raise HTTPException(status_code=400, detail="Brak ALPACA_API_KEY / ALPACA_API_SECRET w .env")

    url = f"{_ALPACA_DATA_BASE}/stocks/{symbol}/bars"
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d")

    params = {
        "timeframe": "1Day",
        "start":     start_date,
        "end":       end_date,
        "limit":     100,
        "feed":      "iex",         # IEX feed działa na darmowym planie
        "sort":      "asc",
    }

    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params, headers=_alpaca_headers())
        response.raise_for_status()
        data = response.json()

    bars = data.get("bars") or []
    if not bars:
        return []

    points: List[PricePoint] = []
    for bar in bars:
        ts_raw = bar.get("t", "")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            continue
        points.append(PricePoint(
            timestamp=ts,
            open=float(bar.get("o", 0)),
            high=float(bar.get("h", 0)),
            low=float(bar.get("l", 0)),
            close=float(bar.get("c", 0)),
            volume=float(bar.get("v", 0)),
        ))

    return points


# ══════════════════════════════════════════════════════════════════
#  Massive.com — historyczne bary dzienne (US stocks, Polygon-compatible API)
#  Dokumentacja: https://massive.com/docs/rest/stocks/aggregates/custom-bars.md
#  Auth: nagłówek Authorization: Bearer {api_key}
#  Limit: do 50 000 punktów / call; obsługuje paginację przez next_url
#  Tylko US exchanges — GPW (.WA) nie jest obsługiwana
# ══════════════════════════════════════════════════════════════════

_MASSIVE_BASE = "https://api.massive.com"


def fetch_stock_prices_from_massive(symbol: str) -> List[PricePoint]:
    """
    Pobiera dzienne bary OHLCV z Massive.com dla podanego tickera (US stocks).
    Endpoint: GET /v2/aggs/ticker/{symbol}/range/1/day/{from}/{to}
    Zwraca do 2 lat historii, posortowane rosnąco po dacie.
    Nie obsługuje GPW (.WA) — używaj tylko dla US stocks.
    """
    if not settings.massive_api_key:
        raise HTTPException(status_code=400, detail="Brak MASSIVE_API_KEY w .env")

    headers = {
        "Authorization": f"Bearer {settings.massive_api_key}",
        "Accept": "application/json",
    }

    today = datetime.now(timezone.utc).date()
    date_from = (today.replace(year=today.year - 2)).isoformat()
    date_to = today.isoformat()

    url = f"{_MASSIVE_BASE}/v2/aggs/ticker/{symbol}/range/1/day/{date_from}/{date_to}"
    params = {"adjusted": "true", "sort": "asc", "limit": 730}

    points: List[PricePoint] = []

    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        next_url: str | None = url
        while next_url:
            if next_url == url:
                response = client.get(next_url, params=params, headers=headers)
            else:
                response = client.get(next_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ERROR":
                raise HTTPException(
                    status_code=502,
                    detail=f"Massive.com error: {data.get('error', 'unknown')}",
                )

            results = data.get("results") or []
            for bar in results:
                ts_ms = bar.get("t", 0)
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                points.append(PricePoint(
                    timestamp=ts,
                    open=float(bar.get("o", 0)),
                    high=float(bar.get("h", 0)),
                    low=float(bar.get("l", 0)),
                    close=float(bar.get("c", 0)),
                    volume=float(bar.get("v", 0)),
                ))

            next_url = data.get("next_url")

    return points


# ══════════════════════════════════════════════════════════════════
#  Twelve Data — historyczne bary dzienne (US stocks, 20 lat historii)
#  Dokumentacja: https://twelvedata.com/docs#time-series
#  Auth: parametr apikey=...
#  Limit: 8 req/min, 800 req/dzień (plan basic)
#  Tylko US exchanges — GPW (.WA) nie jest obsługiwana
# ══════════════════════════════════════════════════════════════════

_TWELVEDATA_BASE = "https://api.twelvedata.com"


def fetch_stock_prices_from_twelvedata(symbol: str) -> List[PricePoint]:
    """
    Pobiera dzienne bary OHLCV z Twelve Data dla podanego tickera (US stocks).
    Endpoint: GET /time_series?symbol={symbol}&interval=1day&outputsize=5000
    Zwraca do 5000 punktów (~20 lat historii), posortowane rosnąco po dacie.
    Nie obsługuje GPW (.WA) — używaj tylko dla US stocks.
    """
    if not settings.twelvedata_api_key:
        raise HTTPException(status_code=400, detail="Brak TWELVEDATA_API_KEY w .env")

    url = f"{_TWELVEDATA_BASE}/time_series"
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 5000,
        "apikey": settings.twelvedata_api_key,
    }

    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    if data.get("status") == "error":
        raise HTTPException(
            status_code=502,
            detail=f"Twelve Data error: {data.get('message', 'unknown')}",
        )

    values = data.get("values")
    if not isinstance(values, list) or not values:
        raise HTTPException(status_code=502, detail=f"Twelve Data: brak danych dla {symbol}")

    # values są posortowane od najnowszego do najstarszego — odwracamy
    points: List[PricePoint] = []
    for bar in reversed(values):
        try:
            ts = datetime.fromisoformat(bar["datetime"]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        points.append(PricePoint(
            timestamp=ts,
            open=float(bar.get("open", 0)),
            high=float(bar.get("high", 0)),
            low=float(bar.get("low", 0)),
            close=float(bar.get("close", 0)),
            volume=float(bar.get("volume", 0)),
        ))

    return points


# ══════════════════════════════════════════════════════════════════
#  RapidAPI — Yahoo Finance (obsługuje GPW .WA oraz US stocks)
#  Dokumentacja: https://rapidapi.com/sparior/api/yahoo-finance15
#  Auth: nagłówek x-rapidapi-key + x-rapidapi-host
#  Limit: zależy od planu; basic plan ~500 req/miesiąc
#  Obsługuje GPW (.WA), NYSE, NASDAQ i inne giełdy
# ══════════════════════════════════════════════════════════════════

_RAPIDAPI_YAHOO_HOST = "yahoo-finance15.p.rapidapi.com"
_RAPIDAPI_YAHOO_BASE = f"https://{_RAPIDAPI_YAHOO_HOST}"


def fetch_stock_prices_from_rapidapi(symbol: str) -> List[PricePoint]:
    """
    Pobiera dzienne bary OHLCV z Yahoo Finance przez RapidAPI.
    Obsługuje zarówno GPW (.WA) jak i US stocks.
    Endpoint: GET /api/v1/markets/stock/history
    Zwraca do 2 lat historii dziennej.
    """
    if not settings.rapidapi_api_key:
        raise HTTPException(status_code=400, detail="Brak RAPIDAPI_API_KEY w .env")

    today = datetime.now(timezone.utc)
    period2 = int(today.timestamp())
    period1 = int((today - timedelta(days=730)).timestamp())

    headers = {
        "x-rapidapi-key":  settings.rapidapi_api_key,
        "x-rapidapi-host": _RAPIDAPI_YAHOO_HOST,
        "Accept": "application/json",
    }
    params = {
        "symbol":         symbol,
        "interval":       "1d",
        "diffandsplits":  "false",
        "period1":        str(period1),
        "period2":        str(period2),
    }

    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        response = client.get(
            f"{_RAPIDAPI_YAHOO_BASE}/api/v1/markets/stock/history",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        data = response.json()

    # Obsługa błędu z API
    if isinstance(data, dict) and data.get("message"):
        raise HTTPException(status_code=502, detail=f"RapidAPI Yahoo Finance error: {data['message']}")

    body = data.get("body") if isinstance(data, dict) else data

    # body może być dict {timestamp_str: {date, open, high, low, close, volume}}
    # lub listą [{date, open, high, low, close, volume}]
    points: List[PricePoint] = []

    if isinstance(body, dict):
        entries = sorted(body.items(), key=lambda kv: kv[0])  # sortuj po kluczu (timestamp)
        for _key, bar in entries:
            if not isinstance(bar, dict):
                continue
            try:
                date_str = bar.get("date") or bar.get("datetime") or ""
                if date_str:
                    ts = datetime.fromisoformat(str(date_str)).replace(tzinfo=timezone.utc)
                else:
                    ts = datetime.fromtimestamp(int(_key), tz=timezone.utc)
                close = float(bar.get("adjclose") or bar.get("close") or 0)
                if close == 0:
                    continue
                points.append(PricePoint(
                    timestamp=ts,
                    open=float(bar.get("open") or close),
                    high=float(bar.get("high") or close),
                    low=float(bar.get("low") or close),
                    close=close,
                    volume=float(bar.get("volume") or 0),
                ))
            except Exception:
                continue

    elif isinstance(body, list):
        for bar in body:
            if not isinstance(bar, dict):
                continue
            try:
                date_str = bar.get("date") or bar.get("datetime") or ""
                ts = datetime.fromisoformat(str(date_str)).replace(tzinfo=timezone.utc)
                close = float(bar.get("adjclose") or bar.get("close") or 0)
                if close == 0:
                    continue
                points.append(PricePoint(
                    timestamp=ts,
                    open=float(bar.get("open") or close),
                    high=float(bar.get("high") or close),
                    low=float(bar.get("low") or close),
                    close=close,
                    volume=float(bar.get("volume") or 0),
                ))
            except Exception:
                continue

    if not points:
        raise HTTPException(status_code=502, detail=f"RapidAPI Yahoo Finance: brak danych dla {symbol}")

    # Sortuj rosnąco po dacie
    points.sort(key=lambda p: p.timestamp)
    return points


# ══════════════════════════════════════════════════════════════════
#  GPW API (gpw-api.p.rapidapi.com) — dedykowane API dla GPW
#  Subskrypcja: plan BASIC (free), daily quota ~100 req/dzień
#  Ticker format: "PKN" (bez .WA)
# ══════════════════════════════════════════════════════════════════

_RAPIDAPI_GPW_HOST = "gpw-api.p.rapidapi.com"
_RAPIDAPI_GPW_BASE = f"https://{_RAPIDAPI_GPW_HOST}"


def fetch_gpw_prices_from_rapidapi(ticker: str) -> List[PricePoint]:
    """
    Pobiera historię cen z GPW API przez RapidAPI.
    ticker: symbol GPW bez .WA, np. "PKN", "CDR", "PKO"
    """
    if not settings.rapidapi_api_key:
        raise HTTPException(status_code=400, detail="Brak RAPIDAPI_API_KEY w .env")

    # Usuń sufiks .WA jeśli przekazano
    clean_ticker = ticker.upper().replace(".WA", "").replace(".WAW", "")

    today = datetime.now(timezone.utc)
    date_to   = today.strftime("%Y-%m-%d")
    date_from = (today - timedelta(days=730)).strftime("%Y-%m-%d")

    headers = {
        "x-rapidapi-key":  settings.rapidapi_api_key,
        "x-rapidapi-host": _RAPIDAPI_GPW_HOST,
        "Accept": "application/json",
    }

    points: List[PricePoint] = []

    with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
        # Próbuj /api/history — główny endpoint historyczny
        resp = client.get(
            f"{_RAPIDAPI_GPW_BASE}/api/history",
            headers=headers,
            params={"ticker": clean_ticker, "from": date_from, "to": date_to},
        )
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and data.get("message"):
        raise HTTPException(status_code=502, detail=f"GPW API: {data['message']}")

    # Normalizuj odpowiedź — może być dict z 'data' lub lista bezpośrednio
    rows = data.get("data") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        # Niektóre API zwracają dict {date: {open,high,low,close,volume}}
        if isinstance(data, dict):
            rows = [{"date": k, **v} for k, v in data.items() if isinstance(v, dict)]
        else:
            rows = []

    for bar in rows:
        if not isinstance(bar, dict):
            continue
        try:
            date_str = (bar.get("date") or bar.get("Date") or bar.get("datetime") or
                        bar.get("time") or bar.get("sessionDate") or "")
            if not date_str:
                continue
            ts = datetime.fromisoformat(str(date_str)[:10]).replace(tzinfo=timezone.utc)
            close = float(bar.get("close") or bar.get("Close") or bar.get("closingPrice") or 0)
            if close == 0:
                continue
            points.append(PricePoint(
                timestamp=ts,
                open=float(bar.get("open")   or bar.get("Open")   or close),
                high=float(bar.get("high")   or bar.get("High")   or close),
                low=float(bar.get("low")     or bar.get("Low")    or close),
                close=close,
                volume=float(bar.get("volume") or bar.get("Volume") or bar.get("turnover") or 0),
            ))
        except Exception:
            continue

    if not points:
        raise HTTPException(status_code=502, detail=f"GPW API: brak danych dla {clean_ticker}")

    points.sort(key=lambda p: p.timestamp)
    return points


# ══════════════════════════════════════════════════════════════════
#  Yahoo Finance v8 API — darmowe dane historyczne bez klucza API
#  Działa dla GPW (.WA), US stocks i innych giełd globalnych
#  Brak limitu dziennego, ~2 lata historii
# ══════════════════════════════════════════════════════════════════

def fetch_gpw_prices_from_stooq(ticker: str) -> List[PricePoint]:
    """
    Pobiera historię cen z Yahoo Finance v8 API (bez klucza API).
    ticker: symbol GPW z .WA, np. "PKN.WA", "KGH.WA"
    Nazwa zachowana dla kompatybilności z sync.py.
    """
    # Upewnij się że ticker ma .WA
    symbol = ticker.upper()
    if not symbol.endswith(".WA"):
        symbol = symbol + ".WA"

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5y"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

    with httpx.Client(timeout=settings.sync_timeout_seconds, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    result = data.get("chart", {}).get("result", [])
    if not result:
        err = data.get("chart", {}).get("error") or "brak danych"
        raise ValueError(f"Yahoo Finance: {err} dla {symbol}")

    timestamps = result[0].get("timestamp", [])
    quote = result[0].get("indicators", {}).get("quote", [{}])[0]
    opens   = quote.get("open",   [])
    highs   = quote.get("high",   [])
    lows    = quote.get("low",    [])
    closes  = quote.get("close",  [])
    volumes = quote.get("volume", [])

    points: List[PricePoint] = []
    for i, ts_epoch in enumerate(timestamps):
        try:
            close = closes[i] if i < len(closes) else None
            if close is None:
                continue
            ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
            points.append(PricePoint(
                timestamp=ts,
                open=float(opens[i])   if i < len(opens)   and opens[i]   is not None else close,
                high=float(highs[i])   if i < len(highs)   and highs[i]   is not None else close,
                low=float(lows[i])     if i < len(lows)    and lows[i]    is not None else close,
                close=float(close),
                volume=float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0.0,
            ))
        except Exception:
            continue

    if not points:
        raise ValueError(f"Yahoo Finance: sparsowano 0 wierszy dla {symbol}")

    points.sort(key=lambda p: p.timestamp)
    return points


def fetch_news_from_alpaca(symbol: str, asset_id: str, asset_type: AssetType) -> List[NewsItem]:
    """
    Pobiera newsy z Alpaca dla podanego symbolu.
    Endpoint: GET /v2/news
    Parametry: symbols, start, end, limit=50
    Alpaca news ma wbudowany sentiment (jeśli dostępny w polu).
    """
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        return []

    url = f"{_ALPACA_DATA_BASE}/news"
    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30)

    params = {
        "symbols": symbol,
        "start":   start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end":     end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit":   50,
        "sort":    "desc",
        "include_content": "false",
    }

    try:
        with httpx.Client(timeout=settings.sync_timeout_seconds) as client:
            response = client.get(url, params=params, headers=_alpaca_headers())
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    items: List[NewsItem] = []
    for article in (data.get("news") or []):
        pub_raw = article.get("created_at") or article.get("updated_at") or ""
        try:
            pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
        except Exception:
            pub_dt = datetime.now(timezone.utc)

        headline = article.get("headline") or ""
        summary  = article.get("summary")  or ""
        url_val  = article.get("url")       or ""
        art_id   = str(article.get("id", ""))

        # Alpaca czasem zawiera wstępny sentiment w polu (niestandard)
        raw_sentiment = float(article.get("sentiment", 0.0) or 0.0)

        items.append(NewsItem(
            id=f"alpaca-{asset_id}-{art_id}",
            asset_id=asset_id,
            source="alpaca:news",
            title=headline,
            body=summary,
            url=url_val,
            published_at=pub_dt,
            sentiment_score=raw_sentiment,
            impact_score=0.65,
        ))

    return items
