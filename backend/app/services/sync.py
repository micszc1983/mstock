from __future__ import annotations

from statistics import median

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AssetORM
from app.repositories.news import upsert_news_item
from app.repositories.prices import upsert_price_point
from app.repositories.sync_logs import add_sync_log
from app.schemas.common import AssetType
from app.schemas.sync import SyncResponse
from app.services.providers import (
    fetch_gpw_news_from_rss,
    fetch_commodity_news_from_rss,
    fetch_gpw_prices_from_eodhd,
    fetch_news_from_newsapi,
    fetch_stock_prices_from_massive,
    fetch_stock_prices_from_rapidapi,
    fetch_gpw_prices_from_rapidapi,
    fetch_prices_from_yahoo,
    fetch_prices_from_yfinance,
    fetch_stock_prices_from_twelvedata,
    fetch_company_news_from_finnhub,
    fetch_company_news_from_finnhub_range,
    fetch_metal_prices_from_alpha_vantage,
    fetch_search_news_from_alpha_vantage,
    fetch_search_news_from_alpha_vantage_range,
    fetch_stock_prices_from_alpha_vantage,
    fetch_quote_from_finnhub,
)
from app.utils.sanitization import redact_sensitive_text


def _provider_secrets() -> tuple[str, ...]:
    return tuple(
        value for value in (
            settings.eodhd_api_key,
            settings.alphavantage_api_key,
            settings.finnhub_api_key,
            settings.newsapi_api_key,
            settings.massive_api_key,
            settings.twelvedata_api_key,
            settings.rapidapi_api_key,
        ) if value
    )


def _safe_provider_error(error: object) -> str:
    detail = getattr(error, "detail", error)
    return redact_sensitive_text(detail, _provider_secrets())


def _crosscheck_closes(primary: list, secondary: list, tolerance_pct: float) -> tuple[bool, str]:
    """Porównuje medianę close z maksymalnie 10 ostatnich wspólnych sesji."""
    primary_by_day = {point.timestamp.date(): float(point.close) for point in primary}
    secondary_by_day = {point.timestamp.date(): float(point.close) for point in secondary}
    common_days = sorted(primary_by_day.keys() & secondary_by_day.keys())[-10:]
    if not common_days:
        return True, "crosscheck=brak wspólnych sesji"
    deviations = [
        abs(primary_by_day[day] / secondary_by_day[day] - 1.0) * 100.0
        for day in common_days
        if secondary_by_day[day] > 0
    ]
    if not deviations:
        return True, "crosscheck=brak porównywalnych cen"
    median_deviation = median(deviations)
    accepted = median_deviation <= max(0.0, tolerance_pct)
    return accepted, (
        f"crosscheck_median_deviation={median_deviation:.3f}%"
        f"/{len(deviations)} sesji; tolerance={tolerance_pct:.3f}%"
    )


def _is_gpw_asset(asset: AssetORM, symbol: str) -> bool:
    return (asset.currency or "").upper() == "PLN" or symbol.upper().endswith((".WA", ".WAW", ".WAR"))


def _is_international_symbol(symbol: str) -> bool:
    """Notowanie spoza USA, które wymaga symbolu giełdy u providera."""
    upper = symbol.upper()
    return upper.endswith((".L", ".SW", ".DE", ".PA", ".MI", ".AS"))


def _news_search_terms(asset: AssetORM, configured: str) -> list[str]:
    """Build precise aliases; ``|`` in assets.json separates query variants."""
    candidates = [*configured.split("|"), asset.name]
    symbol = (asset.symbol or "").upper().split(".", 1)[0]
    # Short tickers are useful in RSS only as whole words (handled by provider).
    if symbol:
        candidates.append(symbol)
    result: list[str] = []
    for value in candidates:
        clean = value.strip()
        if clean and clean.casefold() not in {item.casefold() for item in result}:
            result.append(clean)
    return result[:6]


def _merge_news(primary: list, extra: list) -> list:
    existing_ids = {item.id for item in primary}
    return primary + [item for item in extra if item.id not in existing_ids]



def sync_prices_for_asset(db: Session, asset: AssetORM) -> SyncResponse:
    # Czytaj config z kolumn w AssetORM (nowe podejście — konfiguracja w DB)
    # Fallback do starych ustawień w settings dla kompatybilności wstecznej
    legacy = settings.asset_provider_config.get(asset.id, {})
    inserted = 0
    skipped = 0
    sync_detail = ""

    if asset.type == AssetType.STOCK.value:
        symbol = asset.price_symbol or legacy.get("price_symbol")
        if not symbol:
            raise HTTPException(status_code=400, detail=f"No price symbol configured for {asset.id}. Set price_symbol in asset config.")

        points: list = []
        provider = "unknown"
        is_gpw = _is_gpw_asset(asset, symbol)
        is_international = not is_gpw and _is_international_symbol(symbol)

        # ── GPW: EODHD → Yahoo → opcjonalne RapidAPI ────────────────────────
        if is_gpw:
            # 1. EODHD jest źródłem głównym po ustawieniu klucza.
            if settings.eodhd_api_key and not settings.testing:
                try:
                    provider = "eodhd:eod"
                    points = fetch_gpw_prices_from_eodhd(asset.symbol or symbol)
                    if not points:
                        raise ValueError("EODHD zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: EODHD OK — {len(points)} punktów")
                except Exception as eodhd_err:
                    log_sync_error(db, asset.id, "prices_eodhd_fallback", _safe_provider_error(eodhd_err))
                    points = []

            # Niezależna kontrola EODHD przez Yahoo. Przy systematycznej
            # rozbieżności wybieramy Yahoo, zamiast zapisywać niepewne ceny.
            if points and provider == "eodhd:eod":
                try:
                    yahoo_points = fetch_prices_from_yahoo(symbol)
                    accepted, sync_detail = _crosscheck_closes(
                        points, yahoo_points, settings.gpw_price_crosscheck_tolerance_pct
                    )
                    if not accepted:
                        points = yahoo_points
                        provider = "yahoo:v8:crosscheck-fallback"
                        sync_detail += "; EODHD odrzucone"
                except Exception as crosscheck_err:
                    sync_detail = f"crosscheck_unavailable={_safe_provider_error(crosscheck_err)}"

            # 2. Yahoo — bezpłatny fallback i źródło domyślne bez klucza EODHD.
            if not points:
                try:
                    provider = "yahoo:v8"
                    points = fetch_prices_from_yahoo(symbol)
                    if not points:
                        raise ValueError("Yahoo Finance zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: Yahoo Finance OK — {len(points)} punktów")
                except Exception as yahoo_err:
                    log_sync_error(db, asset.id, "prices_yahoo_fallback", _safe_provider_error(yahoo_err))
                    points = []

            # 3. RapidAPI jest jawnie włączanym fallbackiem. Domyślnie pozostaje
            # wyłączone, aby nie powtarzać 403/429 po wyczerpaniu subskrypcji.
            rapidapi_enabled = settings.rapidapi_price_fallback_enabled and settings.rapidapi_api_key
            if not points and rapidapi_enabled and not settings.testing:
                try:
                    provider = "rapidapi:gpw-api"
                    points = fetch_gpw_prices_from_rapidapi(symbol)
                    if not points:
                        raise ValueError("GPW API zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: GPW API OK — {len(points)} punktów")
                except Exception as gpw_err:
                    log_sync_error(db, asset.id, "prices_gpw_api_fallback", _safe_provider_error(gpw_err))
                    points = []

            if not points and rapidapi_enabled and not settings.testing:
                try:
                    provider = "rapidapi:yahoo-finance"
                    points = fetch_stock_prices_from_rapidapi(symbol)
                    if not points:
                        raise ValueError("RapidAPI zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: RapidAPI Yahoo Finance OK — {len(points)} punktów")
                except Exception as rapi_err:
                    log_sync_error(db, asset.id, "prices_rapidapi_fallback", _safe_provider_error(rapi_err))
                    points = []

        # ── Pozostałe giełdy (np. LSE): yfinance → surowe Yahoo ─────────
        elif is_international:
            try:
                provider = "yfinance:history"
                points = fetch_prices_from_yfinance(symbol)
                if not points:
                    raise ValueError("yfinance zwróciło 0 punktów")
            except Exception as yfinance_err:
                log_sync_error(
                    db, asset.id, "prices_yfinance_fallback",
                    _safe_provider_error(yfinance_err),
                )
                points = []

            if not points:
                try:
                    provider = "yahoo:v8"
                    points = fetch_prices_from_yahoo(symbol)
                    if not points:
                        raise ValueError("Yahoo Finance zwróciło 0 punktów")
                except Exception as yahoo_err:
                    log_sync_error(
                        db, asset.id, "prices_yahoo_fallback",
                        _safe_provider_error(yahoo_err),
                    )
                    points = []

        # ── US stocks: Massive → Twelvedata → RapidAPI → AV → Finnhub ─
        else:
            # 1. Massive.com — priorytet: 2 lata historii, brak limitu dziennego
            if settings.massive_api_key and not settings.testing:
                try:
                    provider = "massive:bars"
                    points = fetch_stock_prices_from_massive(asset.symbol or symbol)
                    if not points:
                        raise ValueError("Massive.com zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: Massive.com OK — {len(points)} punktów")
                except Exception as massive_err:
                    log_sync_error(db, asset.id, "prices_massive_fallback", str(massive_err))
                    points = []

            # 2. Twelve Data — 20 lat historii, 800 req/dzień
            if not points and settings.twelvedata_api_key and not settings.testing:
                try:
                    provider = "twelvedata:time_series"
                    points = fetch_stock_prices_from_twelvedata(asset.symbol or symbol)
                    if not points:
                        raise ValueError("Twelve Data zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: Twelve Data OK — {len(points)} punktów")
                except Exception as td_err:
                    log_sync_error(db, asset.id, "prices_twelvedata_fallback", str(td_err))
                    points = []

            # 3. RapidAPI Yahoo Finance — obsługuje US stocks też
            if (
                not points
                and settings.rapidapi_price_fallback_enabled
                and settings.rapidapi_api_key
                and not settings.testing
            ):
                try:
                    provider = "rapidapi:yahoo-finance"
                    points = fetch_stock_prices_from_rapidapi(asset.symbol or symbol)
                    if not points:
                        raise ValueError("RapidAPI zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: RapidAPI Yahoo Finance OK — {len(points)} punktów")
                except Exception as rapi_err:
                    log_sync_error(db, asset.id, "prices_rapidapi_fallback", str(rapi_err))
                    points = []

            # 5. Alpha Vantage — fallback
            if not points:
                try:
                    provider = "alphavantage:TIME_SERIES_DAILY"
                    points = fetch_stock_prices_from_alpha_vantage(symbol)
                except Exception as av_err:
                    log_sync_error(db, asset.id, "prices_av_fallback", str(av_err))
                    points = []

            # 6. Finnhub quote — ostatni fallback: tylko dzisiejszy punkt
            if not points and settings.finnhub_api_key and not settings.testing:
                try:
                    fh_symbol = asset.symbol or symbol
                    provider = "finnhub:quote"
                    points = fetch_quote_from_finnhub(fh_symbol)
                    if points:
                        print(f"[sync] {asset.id}: wszystkie providery niedostępne — użyto Finnhub quote (1 punkt)")
                except Exception as fh_err:
                    log_sync_error(db, asset.id, "prices_finnhub_fallback", str(fh_err))
                    points = []

        if not points:
            raise HTTPException(
                status_code=502,
                detail=f"Brak danych cenowych dla {asset.id}: żaden provider nie zwrócił danych. Sprawdź klucze API."
            )
    else:
        # Metale: jeśli ma price_symbol → Yahoo Finance (futures GC=F, SI=F itp.) — pełne OHLCV, bez limitu
        price_sym = asset.price_symbol or legacy.get("price_symbol")
        metal_fn  = asset.metal_price_fn or legacy.get("metal_price_fn")

        if price_sym:
            # Yahoo Finance — ten sam provider co GPW, działa dla futures i spot
            try:
                provider = "yahoo:v8"
                points = fetch_prices_from_yahoo(price_sym)
                if not points:
                    raise ValueError("Yahoo Finance zwróciło 0 punktów")
                print(f"[sync] {asset.id}: Yahoo Finance OK — {len(points)} punktów")
            except Exception as yahoo_err:
                log_sync_error(db, asset.id, "prices_yahoo_fallback", str(yahoo_err))
                points = []
            # Fallback: Alpha Vantage jeśli jest metal_fn
            if not points and metal_fn:
                provider = f"alphavantage:{metal_fn}"
                points = fetch_metal_prices_from_alpha_vantage(metal_fn)
        elif metal_fn:
            provider = f"alphavantage:{metal_fn}"
            points = fetch_metal_prices_from_alpha_vantage(metal_fn)
        else:
            raise HTTPException(status_code=400, detail=f"No price_symbol or metal_price_fn configured for {asset.id}.")

    from app.services.ohlcv_validation import validate_bar
    rejected = 0
    for point in points:
        if any(issue.severity == "critical" for issue in validate_bar(point)):
            rejected += 1
            continue
        if upsert_price_point(db, asset.id, point):
            inserted += 1
        else:
            skipped += 1
    db.commit()
    detail = f"Price sync completed; rejected_invalid={rejected}"
    if sync_detail:
        detail += f"; {sync_detail}"
    return SyncResponse(asset_id=asset.id, provider=provider, inserted=inserted, skipped=skipped, detail=detail)


def sync_news_for_asset(db: Session, asset: AssetORM) -> SyncResponse:
    legacy = settings.asset_provider_config.get(asset.id, {})
    inserted = 0
    skipped = 0
    asset_type = AssetType(asset.type)

    news_sym = asset.news_symbol or legacy.get("news_symbol")
    term = asset.news_term or legacy.get("news_term") or asset.name
    terms = _news_search_terms(asset, term)
    price_symbol = asset.price_symbol or legacy.get("price_symbol") or asset.symbol
    is_gpw = _is_gpw_asset(asset, price_symbol)
    is_us_listed = not is_gpw and not _is_international_symbol(price_symbol)

    # Testy integracyjne muszą być całkowicie deterministyczne i nie mogą
    # przypadkiem używać prawdziwych kluczy z backend/.env.
    if settings.testing:
        if asset.type == AssetType.STOCK.value and news_sym:
            provider = "finnhub:company-news:test"
            items = fetch_company_news_from_finnhub(news_sym, asset.id, asset_type)
        else:
            provider = "alphavantage:NEWS_SENTIMENT:test"
            items = fetch_search_news_from_alpha_vantage(term, asset.id, asset_type)

    elif asset.type == AssetType.STOCK.value and (news_sym or is_us_listed) and settings.finnhub_api_key:
        # US stocks z news_symbol — Finnhub company-news (najlepsze źródło dla US)
        provider = "finnhub:company-news"
        items = fetch_company_news_from_finnhub(news_sym or asset.symbol, asset.id, asset_type)
        # ETF-y i mniej popularne tickery mają mało company-news. Zapytanie
        # tematyczne uzupełnia je, ale deduplikacja odrzuci powtórzenia.
        if settings.newsapi_api_key and (asset.sector or "").upper().startswith("ETF"):
            items = _merge_news(
                items,
                fetch_news_from_newsapi(terms, asset.id, asset_type, language="en"),
            )
            provider = "finnhub:company-news+newsapi"

    elif asset.type == AssetType.STOCK.value and is_gpw:
        # GPW: polskie źródła RSS, w tym raporty emitentów PAP/ESPI/EBI.
        # 1. RSS (Bankier, StockWatch, PB) — bez limitu, po polsku
        provider = "rss:gpw"
        items = fetch_gpw_news_from_rss(terms, asset.id, asset_type)
        # 2. NewsAPI — bardziej globalne newsy (EN), 100 req/dzień
        if settings.newsapi_api_key:
            newsapi_items = fetch_news_from_newsapi(terms, asset.id, asset_type, language="pl")
            items = _merge_news(items, newsapi_items)
            if newsapi_items:
                provider = "rss:gpw+newsapi"
        # 3. Finnhub general search — fallback (słabe dla GPW, ale coś)
        if not items and settings.finnhub_api_key:
            provider = "finnhub:general-search"
            from app.services.providers import fetch_search_news_from_finnhub
            items = fetch_search_news_from_finnhub(term, asset.id, asset_type)
        # 4. Alpha Vantage — ostatni fallback
        if not items and (settings.alphavantage_news_fallback_enabled or settings.testing):
            provider = "alphavantage:NEWS_SENTIMENT"
            items = fetch_search_news_from_alpha_vantage(term, asset.id, asset_type)

    elif asset.type == AssetType.METAL.value:
        # Surowce — RSS Kitco/Reuters + NewsAPI
        provider = "rss:commodity"
        items = fetch_commodity_news_from_rss(term, asset.id, asset_type)
        if settings.newsapi_api_key:
            newsapi_items = fetch_news_from_newsapi(terms, asset.id, asset_type, language="en")
            items = _merge_news(items, newsapi_items)
            if newsapi_items:
                provider = "rss:commodity+newsapi"
        if not items and (settings.alphavantage_news_fallback_enabled or settings.testing):
            provider = "alphavantage:NEWS_SENTIMENT"
            items = fetch_search_news_from_alpha_vantage(term, asset.id, asset_type)

    else:
        # ETF-y z giełd europejskich i inne instrumenty bez Finnhub symbol.
        items = []
        if settings.newsapi_api_key:
            provider = "newsapi"
            items = fetch_news_from_newsapi(terms, asset.id, asset_type, language=None)
        if not items and (settings.alphavantage_news_fallback_enabled or settings.testing):
            provider = "alphavantage:NEWS_SENTIMENT"
            items = fetch_search_news_from_alpha_vantage(term, asset.id, asset_type)

    for item in items:
        if upsert_news_item(db, item):
            inserted += 1
        else:
            skipped += 1
    db.commit()
    return SyncResponse(asset_id=asset.id, provider=provider, inserted=inserted, skipped=skipped, detail="News sync completed")


def log_sync_success(db: Session, asset_id: str, sync_type: str, result: SyncResponse) -> None:
    add_sync_log(db, asset_id, sync_type, result.provider, result.inserted, result.skipped, "success", result.detail)
    db.commit()


def log_sync_error(db: Session, asset_id: str, sync_type: str, detail: str) -> None:
    # Po błędzie flush/commit sesja jest w stanie pending rollback i nie
    # przyjmie nawet wpisu diagnostycznego. Odtwórz ją przed zapisem logu.
    if not db.is_active:
        db.rollback()
    add_sync_log(db, asset_id, sync_type, "manual", 0, 0, "error", _safe_provider_error(detail))
    db.commit()


def backfill_news_for_asset(db: Session, asset: AssetORM, months_back: int = 12) -> dict:
    """
    Pobiera historyczne newsy dla aktywa za ostatnie N miesięcy (domyślnie 12).

    Strategia:
    - US stocks z news_symbol: Finnhub company-news po ~30-dniowych oknach
    - Wszystkie aktywa: Alpha Vantage NEWS_SENTIMENT z parametrami time_from/time_to

    Zwraca słownik ze statystykami: inserted, skipped, windows, errors.
    """
    from datetime import date, timedelta as _td
    from app.schemas.common import AssetType as _AT

    legacy = settings.asset_provider_config.get(asset.id, {})
    news_sym = asset.news_symbol or legacy.get("news_symbol")
    term = asset.news_term or legacy.get("news_term") or asset.name
    asset_type = _AT(asset.type)

    inserted = 0
    skipped = 0
    errors = []

    today = date.today()
    start = today - _td(days=months_back * 30)

    # Iteruj po ~60-dniowych oknach żeby nie przekraczać limitów API
    window_days = 60
    cursor = start
    while cursor < today:
        window_end = min(cursor + _td(days=window_days), today)

        # ── Finnhub company-news (US stocks) ──────────────────────────────────
        if asset.type == _AT.STOCK.value and news_sym and settings.finnhub_api_key:
            try:
                items = fetch_company_news_from_finnhub_range(
                    news_sym, asset.id, asset_type,
                    date_from=cursor.isoformat(),
                    date_to=window_end.isoformat(),
                )
                for item in items:
                    if upsert_news_item(db, item):
                        inserted += 1
                    else:
                        skipped += 1
                db.commit()
            except Exception as exc:
                errors.append(f"finnhub {cursor}→{window_end}: {exc}")

        # ── Alpha Vantage NEWS_SENTIMENT (wszystkie aktywa) ───────────────────
        if settings.alphavantage_api_key and term:
            try:
                time_from = cursor.strftime("%Y%m%dT%H%M")
                time_to   = window_end.strftime("%Y%m%dT%H%M")
                items = fetch_search_news_from_alpha_vantage_range(
                    term, asset.id, asset_type, time_from, time_to,
                )
                for item in items:
                    if upsert_news_item(db, item):
                        inserted += 1
                    else:
                        skipped += 1
                db.commit()
            except Exception as exc:
                errors.append(f"alphavantage {cursor}→{window_end}: {exc}")

        cursor = window_end + _td(days=1)

    return {
        "asset_id": asset.id,
        "months_back": months_back,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "detail": f"Backfill zakończony: {inserted} nowych, {skipped} duplikatów, {len(errors)} błędów",
    }
