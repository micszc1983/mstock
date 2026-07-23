from __future__ import annotations


from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.alerts import router as alerts_router
from app.api.routes.assets import router as assets_router
from app.api.routes.decision_support import router as decision_support_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.features import router as features_router
from app.api.routes.ml import router as ml_router
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.nlp import router as nlp_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.reports import router as reports_router
from app.api.routes.watchlists import router as watchlists_router
from app.api.routes.sync import router as sync_router
from app.api.routes.thesis import router as thesis_router
from app.api.routes.quality import router as quality_router
from app.api.routes.data_quality import router as data_quality_router
from app.api.routes.ensemble import router as ensemble_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.earnings import router as earnings_router
from app.api.routes.insider import router as insider_router
from app.api.routes.intraday import router as intraday_router
from app.api.routes.sms_config import router as sms_config_router
from app.api.routes.anomaly import router as anomaly_router
from app.api.routes.simulator import router as simulator_router
from app.api.routes.paper_trading import router as paper_trading_router
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.repositories.assets import list_assets
from app.seed import seed_database
from app.services.feature_builder import rebuild_all_features_and_forecasts
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup ----
    print("[startup] ThesisLab uruchamia się...")
    if settings.testing:
        yield
        return

    # Schemat jest zarządzany wyłącznie przez wersjonowane migracje Alembic.
    # Nie uruchamiaj aplikacji na częściowo zaktualizowanej bazie.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    alembic_cfg = Config(str(Path(__file__).with_name("alembic.ini")))
    alembic_cfg.set_main_option("script_location", str(Path(__file__).with_name("alembic")))
    command.upgrade(alembic_cfg, "head")

    print("[startup] tabele DB gotowe")

    db = SessionLocal()
    try:
        # Opcjonalny, jawnie włączany tryb serwisowy do usuwania danych demo.
        try:
            from app.db.models import (
                PricePointORM, DailyAssetFeatureORM, ForecastORM, ThesisORM,
                ThesisOutcomeORM, DecisionSnapshotORM, AlertORM, EnsembleRecordORM,
                MLTrainingRowORM, MLPredictionORM, SyncLogORM,
            )
            from sqlalchemy import func, delete as _del
            price_count = db.scalar(select(func.count()).select_from(PricePointORM)) or 0
            ok_price_syncs = db.scalar(
                select(func.count()).select_from(SyncLogORM)
                .where(SyncLogORM.sync_type == "prices", SyncLogORM.status.in_(("ok", "success")))
            ) or 0
            if settings.allow_seed_cleanup and price_count > 0 and ok_price_syncs == 0:
                print(f"[startup] wykryto {price_count} rekordów cen bez żadnego udanego syncu — usuwam dane seed")
                for model in [
                    MLPredictionORM, MLTrainingRowORM, EnsembleRecordORM,
                    AlertORM, DecisionSnapshotORM, ThesisOutcomeORM,
                    ForecastORM, DailyAssetFeatureORM, PricePointORM,
                ]:
                    db.execute(_del(model))
                db.commit()
                print("[startup] seed data usunięte — baza gotowa na dane od providerów")
        except Exception as exc:
            print(f"[startup] cleanup seed BŁĄD: {exc}")

        try:
            seed_database(db)
            asset_count = len(list_assets(db))
            print(f"[startup] seed OK — aktywów w bazie: {asset_count}")
        except Exception as exc:
            print(f"[startup] seed BŁĄD: {exc}")

        try:
            from app.repositories.sync_logs import redact_existing_sync_log_secrets
            provider_secrets = tuple(value for value in (
                settings.eodhd_api_key, settings.alphavantage_api_key,
                settings.finnhub_api_key, settings.newsapi_api_key,
                settings.massive_api_key, settings.twelvedata_api_key,
                settings.rapidapi_api_key,
            ) if value)
            redacted = redact_existing_sync_log_secrets(db, provider_secrets)
            if redacted:
                db.commit()
                print(f"[startup] oczyszczono sekrety w {redacted} historycznych logach synchronizacji")
        except Exception as exc:
            db.rollback()
            print(f"[startup] redakcja logów pominięta: {exc}")

        if settings.startup_rebuild_enabled:
            try:
                assets = list_assets(db)
                built = rebuild_all_features_and_forecasts(db, assets)
                print(f"[startup] rebuild OK — zbudowano snapshoty dla {built}/{len(assets)} aktywów")
            except Exception as exc:
                import traceback
                print(f"[startup] rebuild BŁĄD: {exc}")
                traceback.print_exc()
        else:
            print("[startup] ciężki rebuild pominięty; wykona go scheduler")


        # Destrukcyjne porządki tylko po jawnym włączeniu trybu serwisowego.
        try:
            if not settings.allow_seed_cleanup:
                raise RuntimeError("cleanup disabled")
            from sqlalchemy import text
            with db:
                result = db.execute(text("""
                    DELETE FROM price_points
                    WHERE id NOT IN (
                        SELECT MAX(id)
                        FROM price_points
                        GROUP BY asset_id, DATE(timestamp)
                    )
                """))
                removed = result.rowcount
                if removed:
                    db.commit()
                    print(f"[startup] Usunięto {removed} zduplikowanych punktów cenowych")
        except RuntimeError:
            pass
        except Exception as exc:
            print(f"[startup] cleanup duplikatów: {exc}")
        if settings.startup_rebuild_enabled:
            try:
                from app.services.feature_builder import backfill_all_assets
                backfilled = backfill_all_assets(db, days_back=500)
                if backfilled:
                    print(f"[startup] backfill OK — dodano {backfilled} historycznych snapshotów")
                else:
                    print("[startup] backfill — brak nowych snapshotów do dodania")
            except Exception as exc:
                print(f"[startup] backfill skipped: {exc}")
    finally:
        db.close()

    try:
        start_scheduler()
        print("[startup] scheduler uruchomiony")
    except Exception as exc:
        print(f"[startup] scheduler BŁĄD: {exc}")

    print("[startup] ThesisLab gotowy → http://127.0.0.1:8000")
    print("[startup] Sprawdź stan: http://127.0.0.1:8000/health")

    yield  # aplikacja działa

    # ---- shutdown ----
    try:
        stop_scheduler()
    except Exception as exc:
        print(f"[shutdown] scheduler stop skipped: {exc}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Modular ThesisLab backend.",
    lifespan=lifespan,
)


@app.middleware("http")
async def protect_administrative_operations(request: Request, call_next):
    """Chroni administrację i ML; paper trading nie wykonuje operacji zewnętrznych."""
    protected = request.url.path.startswith("/admin") or request.url.path.startswith("/ml/")
    if protected and request.method not in {"GET", "HEAD", "OPTIONS"}:
        import secrets
        client_host = request.client.host if request.client else ""
        supplied = request.headers.get("X-Admin-Key", "")
        configured = settings.admin_api_key
        local_client = client_host in {"127.0.0.1", "::1", "localhost"}
        if not configured and not local_client:
            return JSONResponse(
                status_code=503,
                content={"detail": "ADMIN_API_KEY is required for remote administrative operations"},
            )
        if configured and not secrets.compare_digest(supplied, configured):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing admin key"})
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets_router)
app.include_router(dashboard_router)
app.include_router(thesis_router)
app.include_router(sync_router)
app.include_router(features_router)
app.include_router(quality_router)
app.include_router(alerts_router)
app.include_router(nlp_router)
app.include_router(watchlists_router)
app.include_router(portfolio_router)
app.include_router(reports_router)
app.include_router(notifications_router)
app.include_router(decision_support_router)
app.include_router(ml_router)
app.include_router(evaluation_router)
app.include_router(data_quality_router)
app.include_router(ensemble_router)
app.include_router(recommendations_router)
app.include_router(earnings_router)
app.include_router(insider_router)
app.include_router(intraday_router)
app.include_router(sms_config_router)
app.include_router(anomaly_router)
app.include_router(simulator_router)
app.include_router(paper_trading_router)


# ---------------------------------------------------------------------------
# Health check — pokazuje co jest w bazie i czy dane są gotowe
# ---------------------------------------------------------------------------
from sqlalchemy import text as _sql_text

@app.get("/health")
def health_check(db=Depends(get_db)):
    from app.repositories.assets import list_assets as _la
    assets = _la(db)
    counts = {}
    for table in ("price_points", "daily_asset_features", "forecasts", "theses", "ml_training_rows"):
        try:
            n = db.execute(_sql_text(f"SELECT COUNT(*) FROM {table}")).scalar()
            counts[table] = n
        except Exception:
            counts[table] = "error"
    return {
        "status": "ok", "assets": [a.id for a in assets], "asset_count": len(assets),
        "table_counts": counts, "data_ready": counts.get("daily_asset_features", 0) > 0,
    }


# ---------------------------------------------------------------------------
# Admin: force reseed + rebuild bez potrzeby API keys
# Przydatne gdy /health pokazuje brak danych
# ---------------------------------------------------------------------------
@app.post("/admin/reseed")
def admin_reseed():
    from app.db.session import SessionLocal as _SL
    from app.repositories.assets import list_assets as _la
    from app.seed import seed_database as _seed
    from app.services.feature_builder import rebuild_all_features_and_forecasts as _rebuild
    db = _SL()
    try:
        # Seed normalnie sprawdza czy dane istnieją — tutaj wymuszamy re-run
        # przez tymczasowe obejście: sprawdzamy sami i seediemy jeśli brak cen
        from sqlalchemy import text as _t
        price_count = db.execute(_t("SELECT COUNT(*) FROM price_points")).scalar()
        if price_count == 0:
            _seed(db)
            seeded = True
        else:
            seeded = False

        assets = _la(db)
        built = _rebuild(db, assets)
        return {
            "seeded": seeded,
            "assets": len(assets),
            "features_built": built,
            "message": "Zrobione. Odśwież frontend.",
        }
    except Exception as exc:
        import traceback
        return {"error": str(exc), "traceback": traceback.format_exc()}
    finally:
        db.close()

@app.post("/admin/run-pipeline")
def admin_run_pipeline():
    """Ręczne uruchomienie pełnego cyklu — bez czekania na scheduler."""
    import threading
    from fastapi import Response
    from app.services.scheduler import run_periodic_sync, scheduler_lock

    if not scheduler_lock.acquire(blocking=False):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={"message": "Sync już trwa. Poczekaj na zakończenie bieżącego cyklu.", "running": True},
        )
    scheduler_lock.release()  # Zwolnij natychmiast — run_periodic_sync sam go pobierze

    t = threading.Thread(target=run_periodic_sync, daemon=True)
    t.start()
    return {"message": "Pipeline uruchomiony w tle.", "running": True}


@app.get("/admin/sync-status")
def admin_sync_status():
    """Zwraca czy sync aktualnie trwa."""
    from app.services.scheduler import scheduler_lock
    is_running = not scheduler_lock.acquire(blocking=False)
    if not is_running:
        scheduler_lock.release()
    return {"running": is_running}


@app.get("/admin/scheduler-status")
def admin_scheduler_status():
    from app.services.scheduler import scheduler
    from app.core.config import settings
    jobs = scheduler.get_jobs() if scheduler.running else []
    return {
        "running": scheduler.running,
        "auto_sync_enabled": settings.auto_sync_enabled,
        "interval_minutes": settings.auto_sync_interval_minutes,
        "reports_auto": getattr(settings, "reports_auto_enabled", False),
        "notifications_auto": getattr(settings, "notifications_auto_enabled", False),
        "ml_retrain_auto": getattr(settings, "ml_retrain_auto_enabled", True),
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in jobs
        ],
    }

@app.post("/admin/send-portfolio-report")
def admin_send_portfolio_report():
    """Ręczne wysłanie dziennego raportu portfela emailem."""
    from app.services.scheduler import _send_daily_portfolio_report
    import threading
    t = threading.Thread(target=_send_daily_portfolio_report, daemon=True)
    t.start()
    from app.core.config import settings
    to = settings.report_recipient_email or settings.smtp_from_email or "(nie skonfigurowane)"
    return {"started": True, "to_email": to}


@app.post("/admin/test-sms")
def admin_test_sms():
    """Wysyła testowy SMS przez SIM800C. Używaj do weryfikacji połączenia z modemem."""
    from app.services.sms_service import test_sms
    from app.core.config import settings
    if not settings.sms_enabled:
        return {"sent": False, "reason": "SMS_ENABLED=false w .env"}
    if not settings.sms_recipient_phone:
        return {"sent": False, "reason": "SMS_RECIPIENT_PHONE nie skonfigurowany w .env"}
    sent = test_sms()
    return {"sent": sent, "port": settings.sms_serial_port, "recipient": settings.sms_recipient_phone}


@app.post("/admin/rebuild-ml-predictions")
def admin_rebuild_ml_predictions():
    """Odbuduj tabelę ml_predictions (usuwa i tworzy od nowa, potem uruchamia scoring)."""
    from app.db.session import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        db.execute(text("DROP TABLE IF EXISTS ml_predictions"))
        db.execute(text("""
            CREATE TABLE ml_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id VARCHAR(64) NOT NULL,
                snapshot_at DATETIME NOT NULL,
                model_run_id INTEGER NOT NULL,
                target_name VARCHAR(64) NOT NULL,
                probability_up FLOAT NOT NULL,
                predicted_label VARCHAR(16) NOT NULL,
                raw_json TEXT NOT NULL
            )
        """))
        db.execute(text("CREATE INDEX ix_ml_predictions_asset_id ON ml_predictions(asset_id)"))
        db.execute(text("CREATE INDEX ix_ml_predictions_target_name ON ml_predictions(target_name)"))
        db.execute(text("CREATE INDEX ix_ml_predictions_snapshot_at ON ml_predictions(snapshot_at)"))
        db.commit()
    finally:
        db.close()
    # Uruchom scoring dla wszystkich aktywów w tle
    import threading
    from app.services.scheduler import run_cycle
    t = threading.Thread(target=run_cycle, daemon=True)
    t.start()
    return {"status": "ok", "message": "Tabela ml_predictions odtworzona, scoring uruchomiony w tle"}


@app.post("/admin/backfill-features")
def admin_backfill_features(days_back: int = 60):
    """Jednorazowy backfill historycznych feature snapshotów (buduje dataset ML)."""
    from app.db.session import SessionLocal as _SL
    from app.services.feature_builder import backfill_all_assets
    db = _SL()
    try:
        n = backfill_all_assets(db, days_back=days_back)
        return {"added_snapshots": n, "days_back": days_back,
                "message": f"Dodano {n} snapshotów. Uruchom 'Zbuduj dataset ML' aby zaktualizować liczniki."}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        db.close()

@app.get("/admin/provider-status")
def admin_provider_status(db=None):
    """Status providerów danych: czy klucze są skonfigurowane i kiedy ostatni udany sync."""
    from sqlalchemy import select
    from app.db.models import SyncLogORM
    from app.db.session import SessionLocal
    from app.core.config import settings
    from app.utils.datetime import now_utc
    from datetime import timedelta

    db = SessionLocal()
    try:
        cutoff = now_utc() - timedelta(hours=48)

        def provider_info(provider_prefix: str, key_configured: bool):
            # Ostatni log z tego providera
            last_ok = db.scalar(
                select(SyncLogORM.created_at)
                .where(
                    SyncLogORM.provider.startswith(provider_prefix),
                    SyncLogORM.status.in_(("ok", "success")),
                )
                .order_by(SyncLogORM.created_at.desc()).limit(1)
            )
            last_err = db.scalar(
                select(SyncLogORM.created_at)
                .where(SyncLogORM.provider.startswith(provider_prefix), SyncLogORM.status == "error")
                .order_by(SyncLogORM.created_at.desc()).limit(1)
            )
            errors_24h = db.scalar(
                select(__import__("sqlalchemy").func.count())
                .select_from(SyncLogORM)
                .where(SyncLogORM.provider.startswith(provider_prefix),
                       SyncLogORM.status == "error",
                       SyncLogORM.created_at >= cutoff)
            ) or 0
            return {
                "key_configured": key_configured,
                "last_ok": last_ok.isoformat() if last_ok else None,
                "last_error": last_err.isoformat() if last_err else None,
                "errors_24h": errors_24h,
            }

        return {
            "massive":      provider_info("massive",      bool(settings.massive_api_key)),
            "twelvedata":   provider_info("twelvedata",   bool(settings.twelvedata_api_key)),
            "rapidapi":     provider_info("rapidapi",     bool(settings.rapidapi_api_key)),
"alphavantage": provider_info("alphavantage", bool(settings.alphavantage_api_key)),
            "finnhub":      provider_info("finnhub",      bool(settings.finnhub_api_key)),
        }
    finally:
        db.close()
