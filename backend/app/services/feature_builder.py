from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean

from app.utils.datetime import ensure_utc, now_utc

from sqlalchemy.orm import Session

from app.db.models import AssetORM
from app.mappers import asset_to_schema, news_to_schema, price_to_schema
from app.repositories.features import delete_feature_snapshot_for_timestamp, insert_feature_snapshot
from app.repositories.forecasts import delete_forecast_for_timestamp, insert_forecast
from app.repositories.news import list_news
from app.repositories.prices import list_prices
from app.schemas.features import DailyAssetFeatureSnapshot
from app.services.analytics import build_overview, pct_change
from app.repositories.assets import list_assets
from app.utils.datetime import ensure_utc
from app.services.forecasting import build_forecasts
from app.services.thesis_history import persist_thesis_snapshot




def _calc_volatility_10d(prices) -> float:
    closes = [p.close for p in prices]
    if len(closes) < 11:
        return 0.0
    returns = [pct_change(closes[i], closes[i - 1]) for i in range(1, len(closes))]
    recent = returns[-10:]
    return round(mean(abs(x) for x in recent), 4)


def _calc_momentum_20d(prices) -> float:
    closes = [p.close for p in prices]
    if len(closes) < 21:
        return 0.0
    return round(pct_change(closes[-1], closes[-21]), 4)




def _news_count_7d(news) -> int:
    cutoff = now_utc() - timedelta(days=7)
    return sum(1 for item in news if ensure_utc(item.published_at) >= cutoff)


def rebuild_asset_features_and_forecasts(db: Session, asset_row: AssetORM) -> DailyAssetFeatureSnapshot | None:
    asset = asset_to_schema(asset_row)
    prices = [price_to_schema(row) for row in list_prices(db, asset.id)]
    news = [news_to_schema(row) for row in list_news(db, asset.id)]
    if len(prices) < 21:
        return None

    overview = build_overview(asset, prices, news)
    snapshot_at = prices[-1].timestamp
    snapshot = DailyAssetFeatureSnapshot(
        asset_id=asset.id,
        snapshot_at=snapshot_at,
        last_price=overview.last_price,
        price_change_1d_pct=overview.price_change_1d_pct,
        price_change_5d_pct=overview.price_change_5d_pct,
        price_change_20d_pct=overview.price_change_20d_pct,
        trend_score=overview.trend_score,
        sentiment_score=overview.sentiment_score,
        narrative_shift_score=overview.narrative_shift_score,
        divergence_score=overview.divergence_score,
        fragility_score=overview.fragility_score,
        regime_label=overview.regime,
        regime_confidence=overview.regime_confidence,
        dominant_narrative=overview.dominant_narrative,
        volatility_10d=_calc_volatility_10d(prices),
        momentum_20d=_calc_momentum_20d(prices),
        news_count_7d=_news_count_7d(news),
    )

    # Zachowuj historię: insertuj tylko jeśli nie ma jeszcze snapshotu dla tej daty.
    # To pozwala budować dataset ML z wielu dni, a nie tylko z bieżącego.
    from sqlalchemy import select as _sel, func as _func
    from app.db.models import DailyAssetFeatureORM
    snap_date = snapshot_at.date() if hasattr(snapshot_at, "date") else snapshot_at
    existing_count = db.scalar(
        _sel(_func.count()).select_from(DailyAssetFeatureORM).where(
            DailyAssetFeatureORM.asset_id == asset.id,
            _func.date(DailyAssetFeatureORM.snapshot_at) == snap_date,
        )
    ) or 0
    if existing_count == 0:
        insert_feature_snapshot(db, snapshot)
    else:
        # Aktualizuj istniejący (ceny i sentyment mogą się zmienić w ciągu dnia)
        delete_feature_snapshot_for_timestamp(db, asset.id, snapshot_at)
        insert_feature_snapshot(db, snapshot)

    delete_forecast_for_timestamp(db, asset.id, snapshot_at)
    for forecast in build_forecasts(snapshot):
        forecast.generated_at = snapshot_at
        insert_forecast(db, forecast)

    db.commit()
    persist_thesis_snapshot(db, asset_row, snapshot_at)
    return snapshot


def rebuild_all_features_and_forecasts(db: Session, assets: list[AssetORM]) -> int:
    built = 0
    for asset in assets:
        snapshot = rebuild_asset_features_and_forecasts(db, asset)
        if snapshot is not None:
            built += 1
    return built

def backfill_feature_history(db: Session, asset_row: AssetORM, days_back: int = 60) -> int:
    """
    Buduje historyczne snapshoty feature'ów dla każdego dnia wstecz.
    Używa cenowego rolling window — dla każdego dnia T bierze ceny do T włącznie.
    Zapisuje 1 snapshot per dzień (nie nadpisuje istniejących).
    Zwraca liczbę nowo dodanych snapshotów.
    """
    from datetime import date as _date, timedelta as _td
    from sqlalchemy import select as _sel, func as _func
    from app.db.models import DailyAssetFeatureORM

    asset = asset_to_schema(asset_row)
    all_prices = [price_to_schema(row) for row in list_prices(db, asset.id)]
    news = [news_to_schema(row) for row in list_news(db, asset.id)]

    if len(all_prices) < 21:
        return 0

    # Zbiór dat dla których snapshot już istnieje
    existing_dates: set[_date] = set(
        row.date() if hasattr(row, "date") else ensure_utc(row).date()
        for row in db.scalars(
            _sel(DailyAssetFeatureORM.snapshot_at)
            .where(DailyAssetFeatureORM.asset_id == asset.id)
        ).all()
    )

    # Posortuj ceny chronologicznie
    all_prices_sorted = sorted(all_prices, key=lambda p: ensure_utc(p.timestamp))
    added = 0

    for i in range(20, len(all_prices_sorted)):
        snap_price = all_prices_sorted[i]
        snap_date = ensure_utc(snap_price.timestamp).date()

        # Pomiń jeśli snapshot już istnieje lub poza żądanym oknem
        if snap_date in existing_dates:
            continue
        latest_date = ensure_utc(all_prices_sorted[-1].timestamp).date()
        if (latest_date - snap_date).days > days_back:
            continue

        # Okno cen do tego dnia
        window = all_prices_sorted[:i + 1]
        # Okno newsów do tego dnia (newsów mogło nie być — to OK)
        snap_ts = ensure_utc(snap_price.timestamp)
        news_window = [n for n in news if ensure_utc(n.published_at) <= snap_ts]

        try:
            overview = build_overview(asset, window, news_window)
        except Exception:
            continue

        snapshot = DailyAssetFeatureSnapshot(
            asset_id=asset.id,
            snapshot_at=snap_price.timestamp,
            last_price=overview.last_price,
            price_change_1d_pct=overview.price_change_1d_pct,
            price_change_5d_pct=overview.price_change_5d_pct,
            price_change_20d_pct=overview.price_change_20d_pct,
            trend_score=overview.trend_score,
            sentiment_score=overview.sentiment_score,
            narrative_shift_score=overview.narrative_shift_score,
            divergence_score=overview.divergence_score,
            fragility_score=overview.fragility_score,
            regime_label=overview.regime,
            regime_confidence=overview.regime_confidence,
            dominant_narrative=overview.dominant_narrative,
            volatility_10d=_calc_volatility_10d(window),
            momentum_20d=_calc_momentum_20d(window),
            news_count_7d=_news_count_7d(news_window),
        )
        insert_feature_snapshot(db, snapshot)
        existing_dates.add(snap_date)
        added += 1

    if added > 0:
        db.commit()
    return added


def backfill_all_assets(db: Session, days_back: int = 60) -> int:
    """Backfill dla wszystkich aktywów. Uruchamiaj jednorazowo lub po dodaniu nowych aktywów."""
    total = 0
    for asset_row in list_assets(db):
        n = backfill_feature_history(db, asset_row, days_back=days_back)
        if n > 0:
            print(f"[backfill] {asset_row.id}: +{n} snapshotów")
        total += n
    return total
