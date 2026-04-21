"""
data_quality.py — monitoring jakości danych per aktywo.

Odpowiada na pytania:
  • Czy dane cenowe są aktualne?
  • Ile newsów mamy i ile ma NLP enrichment?
  • Czy features/forecasts/decision snapshots istnieją i nie są przestarzałe?
  • Ile wierszy treningowych ML ma labele?
  • Ile błędów sync w ostatnich 24h / 7 dniach?
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import (
    AssetORM,
    DailyAssetFeatureORM,
    DecisionSnapshotORM,
    ForecastORM,
    MLTrainingRowORM,
    NewsItemORM,
    NewsNLPRunORM,
    PricePointORM,
    SyncLogORM,
)
from app.repositories.assets import list_assets
from app.schemas.data_quality import (
    AssetDataQuality,
    DataQualityReport,
    FeatureQuality,
    MLQuality,
    NewsQuality,
    PriceQuality,
    SyncQuality,
)
from app.utils.datetime import ensure_utc, now_utc


def _hours_ago(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    delta = now_utc() - ensure_utc(dt)
    return round(delta.total_seconds() / 3600, 1)


def _last_trading_day() -> "date":
    """Zwraca ostatni dzień roboczy (pon-pt) włącznie z dzisiaj."""
    from datetime import date
    d = now_utc().date()
    while d.weekday() >= 5:  # sobota=5, niedziela=6
        d -= timedelta(days=1)
    return d


def _is_market_data_stale(last_ts: Optional[datetime], threshold_h: int = 52) -> bool:
    """
    Zwraca True jeśli dane są przestarzałe, uwzględniając weekendy.
    Ceny z ostatniego dnia roboczego (piątek) nie są uznawane za stale
    przez cały weekend — do następnego dnia roboczego + threshold_h.
    """
    if last_ts is None:
        return True
    from datetime import date
    last_date = ensure_utc(last_ts).date()
    last_trading = _last_trading_day()
    # Dane z ostatniego dnia handlowego → nie stale (nawet jeśli minęło >52h)
    if last_date >= last_trading:
        return False
    # Starsze → klasyczny próg
    hours = _hours_ago(last_ts)
    return bool(hours and hours > threshold_h)


def _score_price(q: PriceQuality) -> float:
    s = 0.0
    if q.total_points >= 60:
        s += 0.35
    elif q.total_points >= 21:
        s += 0.20
    elif q.total_points >= 5:
        s += 0.10
    if not q.is_stale:
        s += 0.40
    elif q.staleness_hours and q.staleness_hours < 96:
        s += 0.20
    s += max(0.0, 0.25 * (1.0 - q.gap_pct / 100))
    return round(min(1.0, s), 3)


def _score_news(q: NewsQuality) -> float:
    s = 0.0
    if q.items_7d >= 5:
        s += 0.25
    elif q.items_7d >= 2:
        s += 0.15
    elif q.items_7d >= 1:
        s += 0.08
    if not q.is_stale:
        s += 0.30
    elif q.staleness_hours and q.staleness_hours < 96:
        s += 0.15
    s += 0.25 * min(1.0, q.items_30d / 20)
    s += 0.20 * (q.nlp_coverage_pct / 100)
    return round(min(1.0, s), 3)


def _score_features(q: FeatureQuality) -> float:
    if not q.has_snapshot:
        return 0.0
    s = 0.30
    if not q.is_stale:
        s += 0.30
    if q.scores_nonzero:
        s += 0.15
    if q.has_all_forecasts:
        s += 0.15
    if q.has_decision_snapshot:
        s += 0.10
    return round(min(1.0, s), 3)


def _score_ml(q: MLQuality) -> float:
    s = 0.0
    if q.training_rows >= q.min_required:
        s += 0.40
    elif q.training_rows >= q.min_required // 2:
        s += 0.25
    elif q.training_rows >= 10:
        s += 0.10
    s += 0.40 * (q.label_coverage_pct / 100)
    if q.ready_for_training:
        s += 0.20
    return round(min(1.0, s), 3)


def _score_sync(q: SyncQuality) -> float:
    s = 0.0
    if q.last_successful_sync:
        h = _hours_ago(q.last_successful_sync) or 9999
        if h < 24:
            s += 0.50
        elif h < 72:
            s += 0.30
        elif h < 168:
            s += 0.15
    if q.error_rate_7d < 0.1:
        s += 0.30
    elif q.error_rate_7d < 0.3:
        s += 0.15
    if q.errors_24h == 0:
        s += 0.20
    return round(min(1.0, s), 3)


def _grade(score: float) -> tuple[str, str]:
    if score >= 0.80:
        return "A", "Dobry"
    if score >= 0.60:
        return "B", "Przeciętny"
    if score >= 0.40:
        return "C", "Słaby"
    if score >= 0.20:
        return "D", "Zły"
    return "F", "Krytyczny"


# ── Per-dimension analyzers ────────────────────────────────────────────────────

def _analyze_prices(db: Session, asset_id: str, asset_type: str) -> PriceQuality:
    rows = db.scalars(
        select(PricePointORM)
        .where(PricePointORM.asset_id == asset_id)
        .order_by(PricePointORM.timestamp.asc())
    ).all()

    total = len(rows)
    last_ts = ensure_utc(rows[-1].timestamp) if rows else None
    staleness = _hours_ago(last_ts)
    stale_threshold = 72 if asset_type == "metal" else 52

    # Gap detection: sprawdź ile dni roboczych brakuje w ostatnich 30 dniach
    gap_count = 0
    gap_pct = 0.0
    if rows and len(rows) >= 3:
        # Zbuduj set dat które mamy
        dates_we_have = {ensure_utc(r.timestamp).date() for r in rows}
        today = now_utc().date()
        window_start = today - timedelta(days=30)
        # Policz dni robocze w oknie
        working_days = 0
        missing = 0
        d = window_start
        while d <= today:
            if d.weekday() < 5:  # pon-pt
                working_days += 1
                if d not in dates_we_have:
                    missing += 1
            d += timedelta(days=1)
        gap_count = missing
        gap_pct = round(missing / max(1, working_days) * 100, 1)

    q = PriceQuality(
        total_points=total,
        last_timestamp=last_ts,
        staleness_hours=staleness,
        is_stale=_is_market_data_stale(last_ts, stale_threshold),
        gap_count=gap_count,
        gap_pct=gap_pct,
        score=0.0,
    )
    q.score = _score_price(q)
    return q


def _analyze_news(db: Session, asset_id: str) -> NewsQuality:
    now = now_utc()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    total = db.scalar(
        select(func.count()).select_from(NewsItemORM)
        .where(NewsItemORM.asset_id == asset_id)
    ) or 0

    items_7d = db.scalar(
        select(func.count()).select_from(NewsItemORM)
        .where(NewsItemORM.asset_id == asset_id, NewsItemORM.published_at >= cutoff_7d)
    ) or 0

    items_30d = db.scalar(
        select(func.count()).select_from(NewsItemORM)
        .where(NewsItemORM.asset_id == asset_id, NewsItemORM.published_at >= cutoff_30d)
    ) or 0

    last_news_row = db.scalar(
        select(NewsItemORM.published_at)
        .where(NewsItemORM.asset_id == asset_id)
        .order_by(NewsItemORM.published_at.desc())
        .limit(1)
    )
    last_ts = ensure_utc(last_news_row) if last_news_row else None
    staleness = _hours_ago(last_ts)

    # NLP enrichment coverage — ile newsów ma NLP run
    nlp_enriched = db.scalar(
        select(func.count(NewsNLPRunORM.id.distinct()))
        .where(
            NewsNLPRunORM.news_id.in_(
                select(NewsItemORM.id).where(NewsItemORM.asset_id == asset_id)
            )
        )
    ) or 0
    nlp_pct = round(nlp_enriched / max(1, total) * 100, 1) if total > 0 else 0.0

    q = NewsQuality(
        total_items=total,
        items_7d=items_7d,
        items_30d=items_30d,
        last_timestamp=last_ts,
        staleness_hours=staleness,
        is_stale=_is_market_data_stale(last_ts, 72),
        nlp_enriched=nlp_enriched,
        nlp_coverage_pct=nlp_pct,
        score=0.0,
    )
    q.score = _score_news(q)
    return q


def _analyze_features(db: Session, asset_id: str) -> FeatureQuality:
    feat = db.scalar(
        select(DailyAssetFeatureORM)
        .where(DailyAssetFeatureORM.asset_id == asset_id)
        .order_by(DailyAssetFeatureORM.snapshot_at.desc())
        .limit(1)
    )

    if feat is None:
        q = FeatureQuality(
            has_snapshot=False, staleness_hours=None, is_stale=True,
            scores_nonzero=False, has_all_forecasts=False, has_decision_snapshot=False,
            score=0.0,
        )
        return q

    staleness = _hours_ago(ensure_utc(feat.snapshot_at))
    scores_ok = any([
        abs(feat.trend_score) > 0.01,
        abs(feat.sentiment_score) > 0.01,
        feat.fragility_score > 0.01,
    ])

    horizons_found = db.scalars(
        select(ForecastORM.horizon).where(ForecastORM.asset_id == asset_id)
        .order_by(ForecastORM.generated_at.desc()).limit(9)
    ).all()
    has_all_fc = {"1d", "5d", "20d"}.issubset(set(horizons_found))

    has_decision = db.scalar(
        select(func.count()).select_from(DecisionSnapshotORM)
        .where(DecisionSnapshotORM.asset_id == asset_id)
    ) > 0

    q = FeatureQuality(
        has_snapshot=True,
        staleness_hours=staleness,
        is_stale=_is_market_data_stale(ensure_utc(feat.snapshot_at), 52),
        scores_nonzero=scores_ok,
        has_all_forecasts=has_all_fc,
        has_decision_snapshot=has_decision,
        score=0.0,
    )
    q.score = _score_features(q)
    return q


def _analyze_ml(db: Session, asset_id: str, min_rows: int) -> MLQuality:
    total = db.scalar(
        select(func.count()).select_from(MLTrainingRowORM)
        .where(MLTrainingRowORM.asset_id == asset_id)
    ) or 0

    labeled_5d = db.scalar(
        select(func.count()).select_from(MLTrainingRowORM)
        .where(
            MLTrainingRowORM.asset_id == asset_id,
            MLTrainingRowORM.target_up_5d.isnot(None),
        )
    ) or 0

    labeled_20d = db.scalar(
        select(func.count()).select_from(MLTrainingRowORM)
        .where(
            MLTrainingRowORM.asset_id == asset_id,
            MLTrainingRowORM.target_up_20d.isnot(None),
        )
    ) or 0

    labeled_thesis = db.scalar(
        select(func.count()).select_from(MLTrainingRowORM)
        .where(
            MLTrainingRowORM.asset_id == asset_id,
            MLTrainingRowORM.target_thesis_success.isnot(None),
        )
    ) or 0

    best_labeled = max(labeled_5d, labeled_20d, labeled_thesis)
    label_pct = round(best_labeled / max(1, total) * 100, 1) if total > 0 else 0.0

    q = MLQuality(
        training_rows=total,
        labeled_rows_5d=labeled_5d,
        labeled_rows_20d=labeled_20d,
        labeled_rows_thesis=labeled_thesis,
        label_coverage_pct=label_pct,
        min_required=min_rows,
        ready_for_training=best_labeled >= min_rows,
        score=0.0,
    )
    q.score = _score_ml(q)
    return q


def _analyze_sync(db: Session, asset_id: str) -> SyncQuality:
    now = now_utc()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d  = now - timedelta(days=7)

    logs_7d = db.scalars(
        select(SyncLogORM)
        .where(SyncLogORM.asset_id == asset_id, SyncLogORM.created_at >= cutoff_7d)
        .order_by(SyncLogORM.created_at.desc())
    ).all()

    # Rozróżnij rate-limit (spodziewany przy darmowych kluczach) od prawdziwych błędów
    _RATE_LIMIT_SIGNALS = ("rate limit", "note", "api limit", "api key", "25 requests",
                            "premium", "quota", "too many", "daily limit")

    def _is_rate_limit(detail: str) -> bool:
        d = (detail or "").lower()
        return any(s in d for s in _RATE_LIMIT_SIGNALS)

    errors_all_24h = [l for l in logs_7d
                      if l.status == "error" and ensure_utc(l.created_at) >= cutoff_24h]
    errors_all_7d  = [l for l in logs_7d if l.status == "error"]

    # Błędy konfiguracji = prawdziwe błędy, nie rate-limity
    config_errors_24h = [l for l in errors_all_24h if not _is_rate_limit(l.detail or "")]
    config_errors_7d  = [l for l in errors_all_7d  if not _is_rate_limit(l.detail or "")]

    errors_24h = len(config_errors_24h)
    errors_7d  = len(config_errors_7d)
    total_7d   = len(logs_7d)
    error_rate = round(len(errors_all_7d) / max(1, total_7d), 3)

    last_ok = next(
        (ensure_utc(l.created_at) for l in logs_7d if l.status == "ok"), None
    )
    # Pokaż ostatni prawdziwy błąd konfiguracji, nie rate-limit
    last_error_msg = next(
        (l.detail[:100] for l in config_errors_7d), None
    ) or next(
        (l.detail[:100] for l in errors_all_7d), None
    )

    q = SyncQuality(
        errors_24h=errors_24h,
        errors_7d=errors_7d,
        total_syncs_7d=total_7d,
        error_rate_7d=error_rate,
        last_successful_sync=last_ok,
        last_error=last_error_msg,
        score=0.0,
    )
    q.score = _score_sync(q)
    return q


# ── Issues / warnings builder ─────────────────────────────────────────────────

def _build_issues(
    prices: PriceQuality,
    news: NewsQuality,
    features: FeatureQuality,
    ml: MLQuality,
    sync: SyncQuality,
) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []

    # Ceny
    if prices.total_points == 0:
        issues.append("Brak danych cenowych — nie można budować feature'ów")
    elif prices.is_stale:
        issues.append(f"Ceny przestarzałe ({prices.staleness_hours:.0f}h temu)")
    elif prices.gap_pct > 20:
        warnings.append(f"Duże luki w danych cenowych ({prices.gap_pct:.0f}% dni bez danych)")
    elif prices.gap_pct > 10:
        warnings.append(f"Luki w danych cenowych ({prices.gap_pct:.0f}%)")

    # Newsy
    if news.total_items == 0:
        issues.append("Brak newsów — sentyment = 0, narracje niedostępne. Przyczyną może być brak klucza API (FINNHUB_API_KEY / ALPHAVANTAGE_API_KEY) lub przekroczony limit requestów.")
    elif news.is_stale:
        issues.append(f"Newsy przestarzałe ({news.staleness_hours:.0f}h temu)")
    elif news.items_7d == 0:
        warnings.append("Brak newsów w ostatnich 7 dniach")
    if news.nlp_coverage_pct < 30 and news.total_items > 0:
        warnings.append(f"Niski NLP coverage ({news.nlp_coverage_pct:.0f}%) — uruchom enrichment")

    # Features
    if not features.has_snapshot:
        issues.append("Brak snapshotu feature'ów — dane niedostępne w UI")
    elif features.is_stale:
        warnings.append(f"Feature snapshot przestarzały ({features.staleness_hours:.0f}h temu)")
    if not features.has_all_forecasts:
        warnings.append("Brakuje prognoz dla niektórych horyzontów (1d/5d/20d)")
    if not features.has_decision_snapshot:
        warnings.append("Brak decision snapshot — conviction/risk niedostępne")
    if features.has_snapshot and not features.scores_nonzero:
        issues.append("Feature scores = 0 — prawdopodobnie brak danych wejściowych")

    # ML
    if ml.training_rows == 0:
        warnings.append("Brak wierszy treningowych ML — kliknij 'Zbuduj dataset ML' po kilku dniach działania systemu")
    elif ml.training_rows > 0 and ml.label_coverage_pct < 20:
        if ml.labeled_rows_5d == 0 and ml.labeled_rows_20d == 0:
            warnings.append(f"Brak labeled rows ML — outcomes pojawią się automatycznie po 5-20 dniach od pierwszych tez")
        else:
            warnings.append(f"Niski label coverage ML ({ml.label_coverage_pct:.0f}%) — potrzeba więcej historii (min 5-20 dni)")
    if not ml.ready_for_training and ml.training_rows > 0:
        remaining = ml.min_required - max(ml.labeled_rows_5d, ml.labeled_rows_20d)
        warnings.append(f"Za mało danych do treningu ML (brakuje ~{remaining} labeled rows)")

    # Sync
    if sync.errors_24h >= 5:
        issues.append(f"Dużo błędów konfiguracji sync w 24h ({sync.errors_24h}x) — sprawdź klucze API")
    elif sync.errors_24h >= 2:
        warnings.append(f"Błędy sync w 24h ({sync.errors_24h}x) — mogą być rate-limity lub błędy konfiguracji")
    if sync.total_syncs_7d == 0:
        warnings.append("Brak logów sync w ostatnich 7 dniach — scheduler może nie działać")
    if sync.error_rate_7d > 0.5:
        issues.append(f"Wysoki error rate sync ({sync.error_rate_7d*100:.0f}%) — provider niestabilny")
    if sync.last_error:
        warnings.append(f"Ostatni błąd sync: {sync.last_error[:80]}")

    return issues, warnings


# ── Public API ────────────────────────────────────────────────────────────────

def check_asset_quality(db: Session, asset_row: AssetORM) -> AssetDataQuality:
    from app.core.config import settings
    asset_id = asset_row.id

    prices   = _analyze_prices(db, asset_id, asset_row.type)
    news     = _analyze_news(db, asset_id)
    features = _analyze_features(db, asset_id)
    ml       = _analyze_ml(db, asset_id, settings.ml_min_training_rows)
    sync     = _analyze_sync(db, asset_id)

    # Ważona średnia: prices 30%, news 20%, features 25%, ml 15%, sync 10%
    overall = round(
        prices.score   * 0.30 +
        news.score     * 0.20 +
        features.score * 0.25 +
        ml.score       * 0.15 +
        sync.score     * 0.10,
        3,
    )
    grade, grade_label = _grade(overall)
    issues, warnings = _build_issues(prices, news, features, ml, sync)

    return AssetDataQuality(
        asset_id=asset_id,
        name=asset_row.name,
        symbol=asset_row.symbol,
        asset_type=asset_row.type,
        prices=prices,
        news=news,
        features=features,
        ml=ml,
        sync=sync,
        overall_score=overall,
        grade=grade,
        grade_label=grade_label,
        issues=issues,
        warnings=warnings,
        checked_at=now_utc(),
    )


def check_all_quality(db: Session) -> DataQualityReport:
    assets = list_assets(db)
    results = [check_asset_quality(db, a) for a in assets]
    results.sort(key=lambda r: r.overall_score)  # najgorsze pierwsze

    grades = {g: sum(1 for r in results if r.grade == g) for g in "ABCDF"}
    summary = {
        "total_assets": len(results),
        "grade_distribution": grades,
        "assets_with_issues": sum(1 for r in results if r.issues),
        "assets_ready_for_ml": sum(1 for r in results if r.ml.ready_for_training),
        "avg_overall_score": round(
            sum(r.overall_score for r in results) / max(1, len(results)), 3
        ),
        "stale_prices": sum(1 for r in results if r.prices.is_stale),
        "stale_news": sum(1 for r in results if r.news.is_stale),
        "stale_features": sum(1 for r in results if r.features.is_stale),
        "sync_errors_24h": sum(r.sync.errors_24h for r in results),
    }

    return DataQualityReport(
        assets=results,
        checked_at=now_utc(),
        summary=summary,
    )
