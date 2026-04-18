from __future__ import annotations

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
    fetch_news_from_alpaca,
    fetch_stock_prices_from_alpaca,
    fetch_stock_prices_from_massive,
    fetch_stock_prices_from_rapidapi,
    fetch_gpw_prices_from_rapidapi,
    fetch_gpw_prices_from_stooq,
    fetch_stock_prices_from_twelvedata,
    fetch_company_news_from_finnhub,
    fetch_company_news_from_finnhub_range,
    fetch_metal_prices_from_alpha_vantage,
    fetch_search_news_from_alpha_vantage,
    fetch_search_news_from_alpha_vantage_range,
    fetch_stock_prices_from_alpha_vantage,
    fetch_quote_from_finnhub,
)



def _purge_pre_alpaca_prices(db: Session, asset_id: str, alpaca_points: list) -> None:
    """
    Usuwa stare ceny (seed/fake) które są starsze niż najwcześniejsza data z Alpaca.
    Alpaca ma 7 lat historii — seed data jest zbędna i zakłóca wykresy.
    """
    if not alpaca_points:
        return
    from sqlalchemy import delete
    from app.db.models import PricePointORM
    from app.utils.datetime import ensure_utc

    earliest = min(ensure_utc(p.timestamp) for p in alpaca_points)
    deleted = db.execute(
        delete(PricePointORM).where(
            PricePointORM.asset_id == asset_id,
            PricePointORM.timestamp < earliest,
        )
    ).rowcount
    if deleted:
        print(f"[sync] {asset_id}: usunięto {deleted} seed prices sprzed {earliest.date()}")

def sync_prices_for_asset(db: Session, asset: AssetORM) -> SyncResponse:
    # Czytaj config z kolumn w AssetORM (nowe podejście — konfiguracja w DB)
    # Fallback do starych ustawień w settings dla kompatybilności wstecznej
    legacy = settings.asset_provider_config.get(asset.id, {})
    inserted = 0
    skipped = 0

    if asset.type == AssetType.STOCK.value:
        symbol = asset.price_symbol or legacy.get("price_symbol")
        if not symbol:
            raise HTTPException(status_code=400, detail=f"No price symbol configured for {asset.id}. Set price_symbol in asset config.")

        points: list = []
        provider = "unknown"
        is_gpw = symbol.upper().endswith(".WA")

        # ── GPW (.WA): Yahoo Finance → GPW API → RapidAPI Yahoo Finance → Alpha Vantage ──
        if is_gpw:
            # 1. Yahoo Finance v8 — darmowy, bez klucza, bez limitu, 5 lat historii
            try:
                provider = "yahoo:v8"
                points = fetch_gpw_prices_from_stooq(symbol)  # alias: używa Yahoo Finance v8
                if not points:
                    raise ValueError("Yahoo Finance zwróciło 0 punktów")
                print(f"[sync] {asset.id}: Yahoo Finance OK — {len(points)} punktów")
            except Exception as yahoo_err:
                log_sync_error(db, asset.id, "prices_yahoo_fallback", str(yahoo_err))
                points = []

            # 2. GPW API (gpw-api.p.rapidapi.com) — fallback, limit dzienny
            if not points and settings.rapidapi_api_key:
                try:
                    provider = "rapidapi:gpw-api"
                    points = fetch_gpw_prices_from_rapidapi(symbol)
                    if not points:
                        raise ValueError("GPW API zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: GPW API OK — {len(points)} punktów")
                except Exception as gpw_err:
                    log_sync_error(db, asset.id, "prices_gpw_api_fallback", str(gpw_err))
                    points = []

            # 3. RapidAPI Yahoo Finance — fallback (wymaga subskrypcji yahoo-finance15)
            if not points and settings.rapidapi_api_key:
                try:
                    provider = "rapidapi:yahoo-finance"
                    points = fetch_stock_prices_from_rapidapi(symbol)
                    if not points:
                        raise ValueError("RapidAPI zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: RapidAPI Yahoo Finance OK — {len(points)} punktów")
                except Exception as rapi_err:
                    log_sync_error(db, asset.id, "prices_rapidapi_fallback", str(rapi_err))
                    points = []

            # 4. Alpha Vantage — fallback dla GPW
            if not points:
                try:
                    provider = "alphavantage:TIME_SERIES_DAILY"
                    points = fetch_stock_prices_from_alpha_vantage(symbol)
                    if not points:
                        raise ValueError("Alpha Vantage zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: Alpha Vantage OK — {len(points)} punktów")
                except Exception as av_err:
                    log_sync_error(db, asset.id, "prices_av_fallback", str(av_err))
                    points = []

        # ── US stocks: Massive → Twelvedata → Alpaca → RapidAPI → AV → Finnhub ─
        else:
            # 1. Massive.com — priorytet: 2 lata historii, brak limitu dziennego
            if settings.massive_api_key:
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
            if not points and settings.twelvedata_api_key:
                try:
                    provider = "twelvedata:time_series"
                    points = fetch_stock_prices_from_twelvedata(asset.symbol or symbol)
                    if not points:
                        raise ValueError("Twelve Data zwróciło 0 punktów")
                    print(f"[sync] {asset.id}: Twelve Data OK — {len(points)} punktów")
                except Exception as td_err:
                    log_sync_error(db, asset.id, "prices_twelvedata_fallback", str(td_err))
                    points = []

            # 3. Alpaca — 100 dni historii
            if not points and settings.alpaca_api_key and settings.alpaca_api_secret:
                try:
                    provider = "alpaca:bars"
                    points = fetch_stock_prices_from_alpaca(asset.symbol or symbol)
                    if not points:
                        raise ValueError("Alpaca zwróciło 0 punktów")
                    _purge_pre_alpaca_prices(db, asset.id, points)
                except Exception as alpaca_err:
                    log_sync_error(db, asset.id, "prices_alpaca_fallback", str(alpaca_err))
                    points = []

            # 4. RapidAPI Yahoo Finance — obsługuje US stocks też
            if not points and settings.rapidapi_api_key:
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
            if not points and settings.finnhub_api_key:
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
        metal_fn = asset.metal_price_fn or legacy.get("metal_price_fn")
        if not metal_fn:
            raise HTTPException(status_code=400, detail=f"No metal price function configured for {asset.id}. Set metal_price_fn in asset config.")
        provider = f"alphavantage:{metal_fn}"
        points = fetch_metal_prices_from_alpha_vantage(metal_fn)

    for point in points:
        if upsert_price_point(db, asset.id, point):
            inserted += 1
        else:
            skipped += 1
    db.commit()
    return SyncResponse(asset_id=asset.id, provider=provider, inserted=inserted, skipped=skipped, detail="Price sync completed")


def sync_news_for_asset(db: Session, asset: AssetORM) -> SyncResponse:
    legacy = settings.asset_provider_config.get(asset.id, {})
    inserted = 0
    skipped = 0
    asset_type = AssetType(asset.type)

    news_sym = asset.news_symbol or legacy.get("news_symbol")
    term = asset.news_term or legacy.get("news_term") or asset.name

    if asset.type == AssetType.STOCK.value and news_sym and settings.alpaca_api_key:
        # US stocks — Alpaca news priorytet (50 artykułów / call, brak limitu dziennego)
        provider = "alpaca:news"
        items = fetch_news_from_alpaca(news_sym or asset.symbol, asset.id, asset_type)
        if not items and settings.finnhub_api_key:
            provider = "finnhub:company-news"
            items = fetch_company_news_from_finnhub(news_sym, asset.id, asset_type)
    elif asset.type == AssetType.STOCK.value and news_sym and settings.finnhub_api_key:
        provider = "finnhub:company-news"
        items = fetch_company_news_from_finnhub(news_sym, asset.id, asset_type)
    elif asset.type == AssetType.STOCK.value and not news_sym:
        # Spółki spoza US (GPW): Finnhub general search → fallback Alpha Vantage
        if settings.finnhub_api_key:
            provider = "finnhub:general-search"
            from app.services.providers import fetch_search_news_from_finnhub
            items = fetch_search_news_from_finnhub(term, asset.id, asset_type)
        else:
            items = []
        if not items:
            provider = "alphavantage:NEWS_SENTIMENT"
            items = fetch_search_news_from_alpha_vantage(term, asset.id, asset_type)
    else:
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
    add_sync_log(db, asset_id, sync_type, result.provider, result.inserted, result.skipped, "ok", result.detail)
    db.commit()


def log_sync_error(db: Session, asset_id: str, sync_type: str, detail: str) -> None:
    add_sync_log(db, asset_id, sync_type, "manual", 0, 0, "error", detail)
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
