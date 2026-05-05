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


def _step_sms_critical(db, r: CycleReport) -> None:
    """Wysyła SMS dla nowych alertów krytycznych (status='new', severity='critical')."""
    if not settings.sms_enabled:
        return
    try:
        from app.repositories.alerts import list_alerts
        from app.services.sms_service import send_sms
        from app.utils.datetime import ensure_utc, now_utc
        from datetime import timedelta
        from sqlalchemy import update
        from app.db.models import AlertORM

        cutoff = now_utc() - timedelta(hours=2)
        new_critical = [
            a for a in list_alerts(db, limit=100)
            if a.severity == "critical"
            and a.status == "new"
            and a.created_at and ensure_utc(a.created_at) >= cutoff
        ]
        for alert in new_critical:
            msg = f"MStock ALERT: {alert.title}\n{alert.message}"
            sent = send_sms(msg)
            new_status = "notified_sms" if sent else "active"
            db.execute(
                update(AlertORM)
                .where(AlertORM.id == alert.id)
                .values(status=new_status)
            )
            db.commit()
            if sent:
                r.log(f"SMS wysłany: {alert.alert_type}/{alert.asset_id}")
            else:
                r.err(f"sms/{alert.alert_type}/{alert.asset_id}", Exception("send_sms returned False"))
    except Exception as exc:
        r.err("sms_critical", exc)


# ── Śledzenie Top Picks między cyklami (pamięć in-process) ───────────────────

_prev_top_picks: set[str] = set()
_top_picks_initialized: bool = False


def _step_sms_new_top_pick(db, r: CycleReport) -> None:
    """Wysyła SMS gdy nowe aktywo pojawia się w Top Picks po raz pierwszy w tym cyklu."""
    global _prev_top_picks, _top_picks_initialized
    if not settings.sms_enabled:
        return
    try:
        from app.services.sms_alert_config import get_section
        if not get_section("top_picks_sms").get("enabled", True):
            return
    except Exception:
        pass
    try:
        from app.services.recommendation_engine import build_top_picks
        from app.services.sms_service import send_sms

        current_picks = build_top_picks(db)
        current_ids = {p.asset_id for p in current_picks}

        if not _top_picks_initialized:
            _prev_top_picks = current_ids
            _top_picks_initialized = True
            r.log(f"Top Picks init: {len(current_ids)} aktywow w pierwszym cyklu")
            return

        new_entries = current_ids - _prev_top_picks
        _prev_top_picks = current_ids

        for pick in current_picks:
            if pick.asset_id not in new_entries:
                continue
            msg = (
                f"MStock TOP PICK: {pick.symbol} ({pick.asset_id.upper()}) "
                f"nowe! Pewnosc: {pick.certainty_score * 100:.0f}%, "
                f"Sygnaly: {pick.signals_aligned}/{pick.max_signals}, "
                f"Composite: {pick.composite_score:.0f}"
            )
            sent = send_sms(msg)
            if sent:
                r.log(f"SMS Top Pick nowy: {pick.asset_id}")
            else:
                r.err(f"sms_top_pick/{pick.asset_id}", Exception("send_sms=False"))
    except Exception as exc:
        r.err("sms_new_top_pick", exc)


def _step_sms_portfolio_sell_urgent(db, r: CycleReport) -> None:
    """Wysyła SMS gdy aktywo z portfela ma rekomendację SPRZEDAJ + wysoki risk lub fragility."""
    if not settings.sms_enabled:
        return
    try:
        import json as _json
        from datetime import timedelta

        from sqlalchemy import select, update

        from app.db.models import AlertORM
        from app.repositories.alerts import get_recent_similar_alert, insert_alert
        from app.repositories.assets import get_asset
        from app.repositories.portfolio_positions import list_positions
        from app.services.recommendation_engine import build_recommendation
        from app.services.sms_service import send_sms
        from app.utils.datetime import ensure_utc, now_utc

        try:
            from app.services.sms_alert_config import get_section as _gs
            _psu = _gs("portfolio_sell_urgent")
            if not _psu.get("enabled", True):
                return
            COOLDOWN_MIN = int(_psu.get("cooldown_minutes", 360))
        except Exception:
            COOLDOWN_MIN = 360

        positions = [p for p in list_positions(db) if p.quantity > 0]
        for pos in positions:
            asset = get_asset(db, pos.asset_id)
            if asset is None:
                continue
            try:
                rec = build_recommendation(db, pos.asset_id)
                if rec is None:
                    continue

                is_sell_rec    = rec.recommendation == "SPRZEDAJ"
                is_sell_action = rec.action_label == "SPRZEDAJ"
                high_risk      = (rec.risk_score or 0) >= 65
                high_fragility = rec.fragility_score >= 65

                # Warunek: rekomendacja SPRZEDAJ + przynajmniej jeden dodatkowy sygnał
                if not (is_sell_rec and (is_sell_action or high_risk or high_fragility)):
                    continue

                prev_alert = get_recent_similar_alert(db, pos.asset_id, "portfolio_sell_urgent_sms")
                if prev_alert is not None:
                    age = now_utc() - ensure_utc(prev_alert.created_at)
                    if age < timedelta(minutes=COOLDOWN_MIN):
                        continue

                reasons = []
                if is_sell_action:
                    reasons.append("decision=SPRZEDAJ")
                if high_risk:
                    reasons.append(f"risk={int(rec.risk_score or 0)}")
                if high_fragility:
                    reasons.append(f"fragility={int(rec.fragility_score)}")

                price_str = f"{rec.last_price:.2f}" if rec.last_price else "?"
                msg = (
                    f"MStock PILNE SPRZEDAJ: {rec.symbol} ({pos.asset_id.upper()}) "
                    f"{', '.join(reasons)}. Cena: {price_str} {asset.currency}"
                )
                sent = send_sms(msg)
                title = f"{pos.asset_id.upper()}: pilna sprzedaz z portfela"
                insert_alert(
                    db=db,
                    asset_id=pos.asset_id,
                    created_at=now_utc(),
                    alert_type="portfolio_sell_urgent_sms",
                    severity="critical",
                    title=title,
                    message=msg,
                    status="notified_sms" if sent else "new",
                    trigger_value=float(rec.composite_score),
                    threshold_value=50.0,
                    snapshot_json=_json.dumps({"reasons": reasons, "sent": sent}),
                )
                db.commit()
                if sent:
                    r.log(f"SMS sell urgent: {pos.asset_id} ({', '.join(reasons)})")
                else:
                    r.err(f"sms_sell_urgent/{pos.asset_id}", Exception("send_sms=False"))
            except Exception as exc:
                r.err(f"sms_sell_urgent/{pos.asset_id}", exc)
    except Exception as exc:
        r.err("sms_portfolio_sell_urgent", exc)


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

            # ── Earnings sync (raz na cykl, dla wszystkich aktywów) ────────
            try:
                from app.services.earnings_service import sync_all_earnings
                synced = sync_all_earnings(db)
                if synced:
                    r.log(f"Earnings synced: {sum(synced.values())} records for {len(synced)} assets")
            except Exception as exc:
                r.err("sync_earnings", exc)

            # ── Insider trades + short interest (raz na cykl) ─────────────
            try:
                from app.services.insider_service import sync_all_insider_data
                insider_results = sync_all_insider_data(db)
                total_trades = sum(v.get("insider_trades", 0) for v in insider_results.values())
                total_si = sum(v.get("short_interest", 0) for v in insider_results.values())
                if total_trades or total_si:
                    r.log(f"Insider data synced: {total_trades} trades, {total_si} short interest records")
            except Exception as exc:
                r.err("sync_insider", exc)

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
            _step_sms_critical(db, r)
            _step_sms_new_top_pick(db, r)
            _step_sms_portfolio_sell_urgent(db, r)

    except Exception as exc:
        r.errors.append(f"[fatal] {exc}")
        print(f"[scheduler] FATAL: {exc}")
        traceback.print_exc()
    finally:
        r.finished_at = datetime.now(timezone.utc)
        # Inwaliduj cache rekomendacji — dane zostały właśnie zaktualizowane
        try:
            from app.services.recommendation_engine import invalidate_recommendations_cache
            invalidate_recommendations_cache()
        except Exception:
            pass
        print(f"[scheduler] ═══ {r.summary()} ═══\n")
        scheduler_lock.release()


# ── Start / stop ─────────────────────────────────────────────────────────────

def _send_daily_portfolio_report() -> None:
    """
    Wysyła dzienny raport portfela emailem w dni robocze, 10 minut po zamknięciu giełdy USA.
    Giełda NYSE/NASDAQ zamyka się o 16:00 ET = 22:00 czasu polskiego (niezależnie od DST).
    Job uruchamia się o 22:10 Warsaw — najpierw odświeża ceny i cechy wszystkich aktywów
    z portfela (świeże dane po sesji), a potem wysyła PDF.
    """
    import datetime as _dt
    # Pomiń weekendy (dodatkowe zabezpieczenie oprócz day_of_week w cron)
    weekday = _dt.datetime.now().weekday()  # 0=pon … 6=nie
    if weekday >= 5:
        print("[scheduler] portfolio-report: weekend — pomijam")
        return

    if not settings.smtp_host or not settings.smtp_username:
        print("[scheduler] portfolio-report: SMTP nie skonfigurowane — pomijam")
        return
    to_email = settings.report_recipient_email or settings.smtp_from_email
    if not to_email:
        print("[scheduler] portfolio-report: brak REPORT_RECIPIENT_EMAIL i SMTP_FROM_EMAIL — pomijam")
        return

    from app.db.session import SessionLocal
    from app.repositories.portfolio_positions import list_positions
    from app.repositories.assets import get_asset
    from app.services.portfolio_report import send_portfolio_report

    db = SessionLocal()
    try:
        positions = [p for p in list_positions(db) if p.quantity > 0]
        if not positions:
            print("[scheduler] portfolio-report: brak aktywnych pozycji — pomijam")
            return

        print(f"[scheduler] portfolio-report: odświeżam dane dla {len(positions)} pozycji przed raportem…")

        # ── Krok 1: świeże ceny + cechy dla aktywów z portfela ───────────────
        for pos in positions:
            asset = get_asset(db, pos.asset_id)
            if asset is None:
                continue
            try:
                result = sync_prices_for_asset(db, asset)
                log_sync_success(db, asset.id, "prices", result)
                print(f"[scheduler] portfolio-report: sync cen {asset.id} ({result.inserted} nowych)")
            except Exception as exc:
                print(f"[scheduler] portfolio-report: błąd sync cen {asset.id}: {exc}")
            try:
                rebuild_asset_features_and_forecasts(db, asset)
                print(f"[scheduler] portfolio-report: rebuild features {asset.id} OK")
            except Exception as exc:
                print(f"[scheduler] portfolio-report: błąd rebuild {asset.id}: {exc}")

        # ── Krok 2: pobierz rekomendacje bezpośrednio z serwisu (bez HTTP) ───
        from app.services.recommendation_engine import build_recommendation
        recommendations: dict = {}
        for pos in positions:
            asset = get_asset(db, pos.asset_id)
            if asset is None:
                continue
            try:
                rec = build_recommendation(db, pos.asset_id)
                if rec is None:
                    continue
                recommendations[pos.asset_id] = {
                    "recommendation":  rec.recommendation,
                    "ml_prediction":   rec.ml_prediction,
                    "forecast_dir_5d": rec.forecast_dir_5d,
                    "forecast_dir_20d": rec.forecast_dir_20d,
                    "last_price":      rec.last_price,
                    "currency":        asset.currency,
                }
                print(f"[scheduler] portfolio-report: rec {asset.id} → {rec.recommendation}")
            except Exception as exc:
                print(f"[scheduler] portfolio-report: błąd rekomendacji {pos.asset_id}: {exc}")

        # ── Krok 3: wyślij PDF ────────────────────────────────────────────────
        result = send_portfolio_report(db, recommendations, to_email=to_email)
        status = "✓ OK" if result.get("ok") else "✗ BŁĄD"
        print(f"[scheduler] portfolio-report: {status} — {result.get('detail')}")

    except Exception as exc:
        import traceback as _tb
        print(f"[scheduler] portfolio-report: NIEOCZEKIWANY BŁĄD: {exc}")
        _tb.print_exc()
    finally:
        db.close()


def _handle_sms_commands() -> None:
    """
    Sprawdza skrzynkę SMS modemu SIM800C i obsługuje znane komendy.
    Uruchamiane co 5 minut przez scheduler.

    Obsługiwane komendy (wielkość liter bez znaczenia):
      "raport" — wysyła aktualny raport portfela na maila
    """
    if not settings.sms_enabled:
        return

    try:
        from app.services.sms_service import read_and_clear_sms, send_sms
        messages = read_and_clear_sms()
    except Exception as exc:
        print(f"[sms-cmd] błąd odczytu SMS: {exc}")
        return

    for msg in messages:
        cmd = msg.text.strip().lower().rstrip(".!?,;")
        print(f"[sms-cmd] SMS od {msg.sender}: {msg.text!r} (cmd={cmd!r})")

        if cmd == "raport":
            print(f"[sms-cmd] komenda RAPORT — generuję raport portfela…")
            try:
                _handle_cmd_raport(msg.sender)
            except Exception as exc:
                print(f"[sms-cmd] błąd obsługi komendy raport: {exc}")
                traceback.print_exc()
        else:
            print(f"[sms-cmd] nieznana komenda: {msg.text!r} — ignoruję")


def _handle_cmd_raport(requestor_phone: str) -> None:
    """Generuje i wysyła raport portfela na maila, potwierdzenie SMS."""
    from app.services.sms_service import send_sms

    to_email = settings.report_recipient_email or settings.smtp_from_email
    if not to_email:
        send_sms("MStock: brak REPORT_RECIPIENT_EMAIL w .env - raport niemozliwy.", requestor_phone)
        return

    if not settings.smtp_host or not settings.smtp_username:
        send_sms("MStock: SMTP nie skonfigurowane - raport niemozliwy.", requestor_phone)
        return

    send_sms(f"MStock: generuje raport portfela, wysle na {to_email}...", requestor_phone)

    db = SessionLocal()
    try:
        from app.repositories.portfolio_positions import list_positions
        from app.repositories.assets import get_asset
        from app.services.portfolio_report import send_portfolio_report
        from app.services.recommendation_engine import build_recommendation

        positions = [p for p in list_positions(db) if p.quantity > 0]
        if not positions:
            send_sms("MStock: brak aktywnych pozycji w portfelu.", requestor_phone)
            return

        # Zbierz rekomendacje (bez odświeżania danych — używamy ostatnich znanych)
        recommendations: dict = {}
        for pos in positions:
            asset = get_asset(db, pos.asset_id)
            if asset is None:
                continue
            try:
                rec = build_recommendation(db, pos.asset_id)
                if rec is None:
                    continue
                recommendations[pos.asset_id] = {
                    "recommendation":   rec.recommendation,
                    "ml_prediction":    rec.ml_prediction,
                    "forecast_dir_5d":  rec.forecast_dir_5d,
                    "forecast_dir_20d": rec.forecast_dir_20d,
                    "last_price":       rec.last_price,
                    "currency":         asset.currency,
                }
            except Exception as exc:
                print(f"[sms-cmd] błąd rekomendacji {pos.asset_id}: {exc}")

        result = send_portfolio_report(db, recommendations, to_email=to_email)

        if result.get("ok"):
            send_sms(f"MStock: raport wyslany na {to_email}.", requestor_phone)
            print(f"[sms-cmd] raport wyslany na {to_email}")
        else:
            send_sms(f"MStock: blad wysylki raportu - {result.get('detail', '?')[:80]}", requestor_phone)
            print(f"[sms-cmd] blad raportu: {result.get('detail')}")

    except Exception as exc:
        send_sms(f"MStock: blad generowania raportu: {str(exc)[:80]}", requestor_phone)
        print(f"[sms-cmd] BŁĄD: {exc}")
        traceback.print_exc()
    finally:
        db.close()


def _step_news_alerts() -> None:
    """
    Monitorowanie newsow w czasie rzeczywistym (co 5 min).
    Odpytuje Finnhub dla aktywow z portfela i watchlist.
    Wysluje SMS gdy pojawi sie istotny negatywny news.
    """
    if not settings.sms_enabled or not settings.finnhub_api_key:
        return
    try:
        from app.repositories.assets import get_asset
        from app.repositories.portfolio_positions import list_positions
        from app.repositories.watchlists import list_watchlists, list_watchlist_assets
        from app.services.news_alert_service import scan_recent_news, mark_seen
        from app.services.sms_service import send_sms

        with SessionLocal() as db:
            # Zbierz asset_id: portfel (priorytet) + wszystkie watchlisty
            asset_ids: set[str] = set()
            for pos in list_positions(db):
                if pos.quantity > 0:
                    asset_ids.add(pos.asset_id)
            for wl in list_watchlists(db):
                for aid in list_watchlist_assets(db, wl.id):
                    asset_ids.add(aid)

            # Pobierz symbole — tylko US stocks (Finnhub company-news)
            assets_to_scan: list[tuple[str, str, str | None]] = []
            for aid in asset_ids:
                asset = get_asset(db, aid)
                if asset and asset.type == "stock":
                    assets_to_scan.append((aid, asset.symbol, asset.news_symbol))

        if not assets_to_scan:
            return

        signals = scan_recent_news(assets_to_scan, lookback_minutes=90)
        if not signals:
            return

        seen: list[str] = []
        sent = 0
        for sig in signals[:4]:  # max 4 SMS na cykl, zeby nie spamowac
            headline_short = sig.headline[:110].replace("\n", " ")
            msg = (
                f"MStock NEWS: {sig.symbol} - {headline_short} "
                f"[{sig.source}]"
            )
            ok = send_sms(msg)
            seen.append(sig.news_id)
            if ok:
                sent += 1
                print(
                    f"[news-alert] SMS wyslany: {sig.asset_id} "
                    f"neg={sig.neg_score} '{sig.headline[:60]}'"
                )
            else:
                print(f"[news-alert] SMS blad: {sig.asset_id} '{sig.headline[:60]}'")

        mark_seen(seen)
        if sent:
            print(f"[news-alert] Wyslano {sent} SMS dla {len(signals)} sygnalow")

    except Exception as exc:
        print(f"[news-alert] BLAD: {exc}")
        traceback.print_exc()


def _is_market_hours() -> bool:
    """Zwraca True jeśli aktualny czas mieści się w godzinach sesji NYSE (15:30–22:15 Warsaw)."""
    from zoneinfo import ZoneInfo
    now_pl = datetime.now(ZoneInfo("Europe/Warsaw"))
    # Tylko dni robocze
    if now_pl.weekday() >= 5:
        return False
    minutes = now_pl.hour * 60 + now_pl.minute
    return 15 * 60 + 25 <= minutes <= 22 * 60 + 15  # 15:25–22:15 Warsaw


_fast_check_lock = threading.Lock()
_intraday_lock = threading.Lock()

# ── Pre-market gap alert ──────────────────────────────────────────────────────

# Klucz: asset_id → data (str "YYYY-MM-DD") ostatniego alertu
_premarket_alerted_today: dict[str, str] = {}


def _is_premarket_hours() -> bool:
    """Zwraca True w dni robocze 10:00–15:25 Warsaw (= NYSE pre-market 4:00–9:30 ET)."""
    from zoneinfo import ZoneInfo
    now_pl = datetime.now(ZoneInfo("Europe/Warsaw"))
    if now_pl.weekday() >= 5:
        return False
    minutes = now_pl.hour * 60 + now_pl.minute
    return 10 * 60 <= minutes <= 15 * 60 + 25


def _fetch_premarket_quote(symbol: str) -> dict | None:
    """Pobiera quote z Finnhub: current price, prev close, % change."""
    import httpx
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol.upper(), "token": settings.finnhub_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("c") and data.get("pc"):
            return data
    except Exception as exc:
        print(f"[premarket] błąd Finnhub quote {symbol}: {exc}")
    return None


def _premarket_gap_check() -> None:
    """
    Co 15 min podczas pre-market (10:00–15:25 Warsaw) sprawdza lukę cenową
    dla aktywów z portfela i watchlist.
    SMS wysyłany gdy |gap| >= 3% (portfel) lub >= 5% (watchlist).
    Jeden alert per aktywo per dzień.
    """
    if not settings.sms_enabled or not settings.finnhub_api_key:
        return
    if not _is_premarket_hours():
        return
    try:
        from app.services.sms_alert_config import get_section as _gs
        _pm_cfg = _gs("premarket_gap")
        if not _pm_cfg.get("enabled", True):
            return
    except Exception:
        _pm_cfg = {"portfolio_threshold_pct": 3.0, "watchlist_threshold_pct": 5.0}

    from zoneinfo import ZoneInfo
    today_str = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d")

    try:
        from app.repositories.assets import get_asset
        from app.repositories.portfolio_positions import list_positions
        from app.repositories.watchlists import list_watchlists, list_watchlist_assets
        from app.services.sms_service import send_sms
        import time as _time

        with SessionLocal() as db:
            portfolio_ids: set[str] = set()
            for pos in list_positions(db):
                if pos.quantity > 0:
                    portfolio_ids.add(pos.asset_id)

            watchlist_ids: set[str] = set()
            for wl in list_watchlists(db):
                for aid in list_watchlist_assets(db, wl.id):
                    watchlist_ids.add(aid)

            # Zbierz wszystkie unikalne stock assets
            all_ids = portfolio_ids | watchlist_ids
            candidates: list[tuple[str, str, float]] = []  # (asset_id, symbol, threshold)
            for aid in all_ids:
                asset = get_asset(db, aid)
                if asset is None or asset.type != "stock":
                    continue
                symbol = (asset.price_symbol or asset.symbol or "").upper()
                if not symbol:
                    continue
                threshold = float(_pm_cfg.get("portfolio_threshold_pct", 3.0)) if aid in portfolio_ids else float(_pm_cfg.get("watchlist_threshold_pct", 5.0))
                candidates.append((aid, symbol, threshold))

        if not candidates:
            return

        sent_count = 0
        for i, (asset_id, symbol, threshold) in enumerate(candidates):
            if i > 0:
                _time.sleep(0.3)  # Finnhub rate limit

            # Już wysłano alert dla tego aktywa dziś?
            if _premarket_alerted_today.get(asset_id) == today_str:
                continue

            quote = _fetch_premarket_quote(symbol)
            if quote is None:
                continue

            current = quote["c"]
            prev_close = quote["pc"]
            gap_pct = (current - prev_close) / prev_close * 100

            if abs(gap_pct) < threshold:
                continue

            direction = "+" if gap_pct > 0 else ""
            msg = (
                f"MStock PRE-MARKET: {symbol} {direction}{gap_pct:.1f}% przed sesja. "
                f"Cena: {current:.2f} USD (zamkniecie: {prev_close:.2f})"
            )
            ok = send_sms(msg)
            _premarket_alerted_today[asset_id] = today_str

            tag = "portfel" if asset_id in portfolio_ids else "watchlist"
            status = "✓" if ok else "✗"
            print(f"[premarket] {status} SMS gap {symbol}: {direction}{gap_pct:.1f}% [{tag}]")
            if ok:
                sent_count += 1

        if sent_count:
            print(f"[premarket] Wysłano {sent_count} alertów gap")

    except Exception as exc:
        print(f"[premarket] BŁĄD: {exc}")
        import traceback as _tb
        _tb.print_exc()


_intraday_sms_sent: dict[str, str] = {}  # asset_id -> "BUY/SELL@timestamp"


def _sync_intraday_job() -> None:
    """Sync świec intraday dla wszystkich stocks — uruchamiany co 15 min podczas sesji NYSE."""
    if not _is_market_hours():
        return
    if not _intraday_lock.acquire(blocking=False):
        return
    try:
        from app.services.intraday_service import sync_all_intraday, get_latest_signals
        from app.services.sms_alert_config import get_section
        with SessionLocal() as db:
            results = sync_all_intraday(db, resolutions=["15", "60"])
            if results:
                total = sum(results.values())
                print(f"[intraday-sync] Nowe świece: {total} dla {len(results)} aktywów")
                # SMS dla silnych sygnałów intraday (tylko gdy są nowe świece)
                intraday_cfg = get_section("intraday_sms")
                if intraday_cfg.get("enabled", True):
                    min_strength = intraday_cfg.get("min_strength", 60)
                    _check_intraday_sms(db, results, min_strength, get_latest_signals)
    except Exception as exc:
        print(f"[intraday-sync] BŁĄD: {exc}")
    finally:
        _intraday_lock.release()


def _check_intraday_sms(db, updated_assets: dict, min_strength: int, get_latest_signals_fn) -> None:
    """Sprawdza sygnały intraday i wysyła SMS gdy siła >= min_strength."""
    today = _dt.date.today().isoformat()
    for asset_id in updated_assets:
        try:
            data = get_latest_signals_fn(db, asset_id, resolution="15")
            for sig in data.get("signals", []):
                if sig["strength"] < min_strength:
                    continue
                key = f"{asset_id}:{sig['type']}:{today}"
                if key in _intraday_sms_sent:
                    continue
                _intraday_sms_sent[key] = sig["timestamp"]
                reasons_str = ", ".join(sig["reasons"][:3])
                msg = (
                    f"INTRADAY {sig['type']} {asset_id.upper()}\n"
                    f"Cena: ${sig['price']:.2f} | Sila: {sig['strength']}%\n"
                    f"{reasons_str}"
                )
                _send_sms(msg)
                print(f"[intraday-sms] {sig['type']} {asset_id} strength={sig['strength']}")
        except Exception as exc:
            print(f"[intraday-sms] blad {asset_id}: {exc}")


def _fast_price_and_alert_check() -> None:
    """
    Lekki job uruchamiany co 15 min w trakcie sesji NYSE (15:30–22:15 PL).
    Robi tylko: sync cen + alert engine + SMS krytyczny.
    Nie zastępuje pełnego pipeline'u — działa równolegle jako uzupełnienie.
    """
    if not _is_market_hours():
        return

    if not _fast_check_lock.acquire(blocking=False):
        print("[fast-check] Poprzedni fast-check nadal trwa — pomijam.")
        return

    r = CycleReport()
    print(f"[fast-check] Szybki sync cen + alerty ({datetime.now(timezone.utc).strftime('%H:%M UTC')})")

    try:
        with SessionLocal() as db:
            assets = db.scalars(select(AssetORM).order_by(AssetORM.name.asc())).all()

            for asset in assets:
                _step_sync_prices(db, asset, r)
                _step_alerts(db, asset, r)

            _step_sms_critical(db, r)
            _step_sms_portfolio_sell_urgent(db, r)

        if r.assets_alerts_fired:
            print(f"[fast-check] Alerty: {r.assets_alerts_fired}, SMS: {r.notifications_sent}, błędy: {len(r.errors)}")
        if r.errors:
            for e in r.errors:
                print(f"[fast-check] ✗ {e}")
    except Exception as exc:
        print(f"[fast-check] BŁĄD: {exc}")
        traceback.print_exc()
    finally:
        _fast_check_lock.release()


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
    scheduler.add_job(
        _send_daily_portfolio_report,
        "cron",
        day_of_week="mon-fri",  # tylko dni robocze
        hour=22,
        minute=10,              # 10 min po zamknięciu NYSE/NASDAQ (16:00 ET = 22:00 PL)
        timezone="Europe/Warsaw",
        id="portfolio-report",
        replace_existing=True,
    )
    scheduler.add_job(
        _fast_price_and_alert_check,
        "interval",
        minutes=15,
        id="fast-price-check",
        replace_existing=True,
    )
    if settings.finnhub_api_key:
        scheduler.add_job(
            _sync_intraday_job,
            "interval",
            minutes=15,
            id="intraday-sync",
            replace_existing=True,
        )
        print("[scheduler] Intraday sync co 15 min (tylko podczas sesji NYSE)")
    if settings.sms_enabled and settings.finnhub_api_key:
        scheduler.add_job(
            _premarket_gap_check,
            "interval",
            minutes=15,
            id="premarket-gap",
            replace_existing=True,
        )
        print("[scheduler] Pre-market gap alert co 15 min (10:00–15:25 Warsaw)")
    # News SMS wyłączone — alerty oparte na cenie/ML są precyzyjniejsze
    # if settings.finnhub_api_key:
    #     scheduler.add_job(_step_news_alerts, "interval", minutes=5, id="news-alerts", replace_existing=True)
    if settings.sms_enabled:
        scheduler.add_job(
            _handle_sms_commands,
            "interval",
            minutes=5,
            id="sms-commands",
            replace_existing=True,
        )
        print("[scheduler] SMS polling co 5 min włączony")
    scheduler.start()
    print(f"[scheduler] Uruchomiony — cykl co {settings.auto_sync_interval_minutes} min, fast-check co 15 min podczas sesji, raport portfela pn-pt o 22:10")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[scheduler] Zatrzymany.")
