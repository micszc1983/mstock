"""
scheduler.py — pełna automatyzacja ThesisLab.

Pipeline uruchamia się co AUTO_SYNC_INTERVAL_MINUTES (domyślnie 60 min).

Kolejność kroków (każdy chroniony osobnym try/except):
  Per aktywo:
    1.  Sync cen
    2.  Sync newsów
    3.  Enrichment NLP (FinBERT / heuristic)
    4.  Rebuild features + forecasts
    5.  Persist decision snapshot
    6.  Ewaluacja outcomes dla historycznych tez
    7.  Alert engine
  Globalnie (po wszystkich aktywach):
    8.  Build ML training dataset
    9.  Retrenuj modele ML (jeśli wystarczy danych)
    10. Generuj raporty dzienne (jeśli REPORTS_AUTO_ENABLED=true)
    11. Wyślij notyfikacje o alertach (jeśli są nowe krytyczne)

Konfiguracja w backend/.env:
  AUTO_SYNC_ENABLED=true
  AUTO_SYNC_INTERVAL_MINUTES=60
  REPORTS_AUTO_ENABLED=false         # generowanie PDF co cykl
  NOTIFICATIONS_AUTO_ENABLED=false   # wysyłka email/WhatsApp o alertach
  ML_RETRAIN_AUTO_ENABLED=true       # retrenowanie ML po builddzie datasetu
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.core.config import settings
from app.db.models import AssetORM
from app.db.session import SessionLocal
from app.schemas.common import AssetType
from app.services.alert_engine import run_alert_engine
from app.services.decision_support import persist_decision_snapshot
from app.services.feature_builder import rebuild_asset_features_and_forecasts
from app.services.ml_foundation import build_training_dataset, train_all_targets
from app.services.news_enrichment import enrich_news_for_asset
from app.services.ensemble_engine import fill_ensemble_outcomes, build_ensemble_signal, DEFAULT_CONFIG
from app.services.outcome_evaluator import evaluate_asset_outcomes
from app.core.config import settings
from app.services.sync import log_sync_error, log_sync_success, sync_news_for_asset, sync_prices_for_asset


scheduler = BackgroundScheduler(timezone="UTC")
scheduler_lock = threading.Lock()


# ── Raport z cyklu ────────────────────────────────────────────────────────────

@dataclass
class CycleReport:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    assets_synced: int = 0
    assets_news_synced: int = 0
    assets_enriched: int = 0
    assets_features_built: int = 0
    assets_decisions_built: int = 0
    assets_outcomes_evaluated: int = 0
    assets_alerts_fired: int = 0
    ml_dataset_rows: int = 0
    ml_trained_targets: list[str] = field(default_factory=list)
    reports_generated: int = 0
    notifications_sent: int = 0
    errors: list[str] = field(default_factory=list)

    def err(self, step: str, exc: Exception) -> None:
        msg = f"[{step}] {type(exc).__name__}: {exc}"
        self.errors.append(msg)
        print(f"  ✗ {msg}")

    def log(self, msg: str) -> None:
        print(f"  ✓ {msg}")

    def summary(self) -> str:
        secs = (
            (self.finished_at - self.started_at).total_seconds()
            if self.finished_at else 0
        )
        return (
            f"Cykl ukończony w {secs:.1f}s | "
            f"sync_prices={self.assets_synced} "
            f"sync_news={self.assets_news_synced} "
            f"enriched={self.assets_enriched} "
            f"features={self.assets_features_built} "
            f"decisions={self.assets_decisions_built} "
            f"outcomes={self.assets_outcomes_evaluated} "
            f"alerts={self.assets_alerts_fired} "
            f"ml_rows={self.ml_dataset_rows} "
            f"ml_trained={self.ml_trained_targets} "
            f"reports={self.reports_generated} "
            f"notifications={self.notifications_sent} "
            f"errors={len(self.errors)}"
        )


# ── Pomocnicze gettery konfiguracji ──────────────────────────────────────────

def _reports_auto() -> bool:
    return getattr(settings, "reports_auto_enabled", False)

def _notifications_auto() -> bool:
    return getattr(settings, "notifications_auto_enabled", False)

def _ml_retrain_auto() -> bool:
    return getattr(settings, "ml_retrain_auto_enabled", True)


# ── Kroki pipeline'u ─────────────────────────────────────────────────────────

def _step_sync_prices(db, asset: AssetORM, r: CycleReport) -> None:
    needs_price_sync = (
        asset.id in {"gold", "silver"}
        or asset.type == AssetType.STOCK.value
        or asset.type == "metal"
    )
    if not needs_price_sync:
        return
    try:
        result = sync_prices_for_asset(db, asset)
        log_sync_success(db, asset.id, "prices", result)
        r.assets_synced += 1
        r.log(f"{asset.id}: ceny sync ({result.inserted} nowych)")
    except Exception as exc:
        log_sync_error(db, asset.id, "prices", str(exc))
        r.err(f"sync_prices/{asset.id}", exc)


def _step_sync_news(db, asset: AssetORM, r: CycleReport) -> None:
    try:
        result = sync_news_for_asset(db, asset)
        log_sync_success(db, asset.id, "news", result)
        r.assets_news_synced += 1
        r.log(f"{asset.id}: newsy sync ({result.inserted} nowych)")
    except Exception as exc:
        log_sync_error(db, asset.id, "news", str(exc))
        r.err(f"sync_news/{asset.id}", exc)


def _step_nlp_enrichment(db, asset: AssetORM, r: CycleReport) -> None:
    try:
        enriched = enrich_news_for_asset(db, asset.id, limit=30)
        r.assets_enriched += 1
        r.log(f"{asset.id}: NLP enrichment ({enriched} newsów)")
    except Exception as exc:
        r.err(f"nlp_enrichment/{asset.id}", exc)


def _step_rebuild_features(db, asset: AssetORM, r: CycleReport) -> None:
    try:
        snapshot = rebuild_asset_features_and_forecasts(db, asset)
        if snapshot:
            r.assets_features_built += 1
            r.log(f"{asset.id}: features + forecasts rebuilt")
    except Exception as exc:
        r.err(f"rebuild_features/{asset.id}", exc)


def _step_decision_snapshot(db, asset: AssetORM, r: CycleReport) -> None:
    try:
        snap = persist_decision_snapshot(db, asset.id)
        if snap:
            r.assets_decisions_built += 1
            r.log(f"{asset.id}: decision snapshot ({snap.action_label})")
    except Exception as exc:
        r.err(f"decision_snapshot/{asset.id}", exc)


def _step_outcomes(db, asset: AssetORM, r: CycleReport) -> None:
    try:
        count = evaluate_asset_outcomes(db, asset.id, limit=200)
        if count > 0:
            r.assets_outcomes_evaluated += count
            r.log(f"{asset.id}: outcomes evaluated ({count})")
    except Exception as exc:
        r.err(f"outcomes/{asset.id}", exc)


def _step_alerts(db, asset: AssetORM, r: CycleReport) -> None:
    try:
        fired = run_alert_engine(db, asset.id)
        r.assets_alerts_fired += fired
        if fired:
            r.log(f"{asset.id}: {fired} alert(ów) wygenerowanych")
    except Exception as exc:
        r.err(f"alerts/{asset.id}", exc)


def _step_ml_dataset(db, r: CycleReport) -> None:
    try:
        result = build_training_dataset(db)
        r.ml_dataset_rows = result.total_rows
        r.log(f"ML dataset: {result.built_rows} nowych wierszy, łącznie {result.total_rows}")
    except Exception as exc:
        r.err("ml_dataset", exc)


def _step_ml_train(db, r: CycleReport) -> None:
    if not _ml_retrain_auto():
        return
    try:
        results = train_all_targets(db)
        trained = [res["target"] for res in results if not res.get("skipped")]
        skipped = [res["target"] for res in results if res.get("skipped")]
        r.ml_trained_targets = trained
        if trained:
            r.log(f"ML trained: {trained}")
        if skipped:
            r.log(f"ML skipped (za mało danych): {skipped}")
    except Exception as exc:
        r.err("ml_train", exc)


def _step_reports(db, assets: list[AssetORM], r: CycleReport) -> None:
    if not _reports_auto():
        return
    from app.services.report_service import generate_asset_daily_report
    for asset in assets:
        try:
            _, fname = generate_asset_daily_report(db, asset.id)
            r.reports_generated += 1
            r.log(f"Raport PDF: {fname}")
        except Exception as exc:
            r.err(f"report/{asset.id}", exc)


def _step_notifications(db, r: CycleReport) -> None:
    if not _notifications_auto():
        return
    if r.assets_alerts_fired == 0:
        return  # brak nowych alertów → nie wysyłaj

    from app.repositories.notifications import list_notification_channels
    from app.repositories.alerts import list_alerts
    from app.services.notification_service import send_email_notification, send_whatsapp_notification

    channels = [ch for ch in list_notification_channels(db) if ch.is_enabled]
    if not channels:
        return

    # Zbierz nowe aktywne alerty (z ostatnich ~2 godzin)
    from app.utils.datetime import now_utc
    from datetime import timedelta
    cutoff = now_utc() - timedelta(hours=2)
    recent_alerts = [
        a for a in list_alerts(db, limit=50)
        if a.status == "active" and a.created_at and a.created_at >= cutoff
    ]
    if not recent_alerts:
        return

    lines = [f"• [{a.severity.upper()}] {a.asset_id.upper()}: {a.title}" for a in recent_alerts[:10]]
    message = f"ThesisLab Alerty ({len(recent_alerts)}):\n" + "\n".join(lines)

    for channel in channels:
        try:
            if channel.channel_type == "email":
                result = send_email_notification(
                    db, channel.id,
                    subject=f"ThesisLab: {len(recent_alerts)} nowych alertów",
                    message=message,
                )
                if result.get("sent"):
                    r.notifications_sent += 1
                    r.log(f"Email wysłany: {channel.target}")
            elif channel.channel_type == "whatsapp":
                result = send_whatsapp_notification(db, channel.id, message=message)
                if result.get("sent"):
                    r.notifications_sent += 1
                    r.log(f"WhatsApp wysłany: {channel.target}")
        except Exception as exc:
            r.err(f"notify/{channel.channel_type}/{channel.id}", exc)


# ── Główna funkcja cyklu ─────────────────────────────────────────────────────

def run_periodic_sync() -> None:
    if not scheduler_lock.acquire(blocking=False):
        print("[scheduler] Poprzedni cykl nadal trwa — pomijam.")
        return

    r = CycleReport()
    print(f"\n[scheduler] ═══ Start cyklu {r.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')} ═══")

    try:
        with SessionLocal() as db:
            assets = db.scalars(
                select(AssetORM).order_by(AssetORM.name.asc())
            ).all()

            # ── Per-asset steps ────────────────────────────────────────────
            for asset in assets:
                print(f"[scheduler] → {asset.id}")
                _step_sync_prices(db, asset, r)
                _step_sync_news(db, asset, r)
                _step_nlp_enrichment(db, asset, r)
                _step_rebuild_features(db, asset, r)
                _step_decision_snapshot(db, asset, r)
                _step_outcomes(db, asset, r)
                _step_alerts(db, asset, r)

            # ── Global steps ───────────────────────────────────────────────
            print("[scheduler] → ML pipeline")
            _step_ml_dataset(db, r)
            _step_ml_train(db, r)

            # Zapisz sygnały ensemble dla wszystkich aktywów (buduje historię dla leaderboard)
            ensemble_saved = 0
            for asset in assets:
                try:
                    build_ensemble_signal(db, asset.id, DEFAULT_CONFIG, save_record=True)
                    ensemble_saved += 1
                except Exception as exc:
                    r.err(f"ensemble_record_{asset.id}", exc)
            if ensemble_saved:
                r.log(f"Ensemble records saved: {ensemble_saved}")

            # Backfill ensemble outcomes (uzupełnia winner dla rekordów starszych niż 5d)
            try:
                filled = fill_ensemble_outcomes(db)
                if filled:
                    r.log(f"Ensemble outcomes backfilled: {filled}")
            except Exception as exc:
                r.err("fill_ensemble_outcomes", exc)

            print("[scheduler] → Raporty i notyfikacje")
            _step_reports(db, assets, r)
            _step_notifications(db, r)

    except Exception as exc:
        r.errors.append(f"[fatal] {exc}")
        print(f"[scheduler] FATAL: {exc}")
        traceback.print_exc()
    finally:
        r.finished_at = datetime.now(timezone.utc)
        print(f"[scheduler] ═══ {r.summary()} ═══\n")
        scheduler_lock.release()


# ── Start / stop ─────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    if not settings.auto_sync_enabled:
        print("[scheduler] Wyłączony (AUTO_SYNC_ENABLED=false)")
        return
    if scheduler.running:
        return
    scheduler.add_job(
        run_periodic_sync,
        "interval",
        minutes=settings.auto_sync_interval_minutes,
        id="full-pipeline",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[scheduler] Uruchomiony — cykl co {settings.auto_sync_interval_minutes} min")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[scheduler] Zatrzymany.")
