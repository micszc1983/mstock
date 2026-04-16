from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.alerts import list_alerts_for_asset
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.theses import get_latest_thesis
from app.repositories.watchlists import get_watchlist, list_watchlist_assets


def _ensure_reports_dir() -> Path:
    path = Path(settings.reports_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _draw_lines(pdf: canvas.Canvas, x: int, y: int, lines: list[str], step: int = 16) -> int:
    current_y = y
    for line in lines:
        pdf.drawString(x, current_y, line[:110])
        current_y -= step
    return current_y


def generate_asset_daily_report(db: Session, asset_id: str) -> tuple[str, str]:
    out_dir = _ensure_reports_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_name = f"daily_report_{asset_id}_{ts}.pdf"
    file_path = out_dir / file_name

    feature = get_latest_feature_snapshot(db, asset_id)
    thesis = get_latest_thesis(db, asset_id)
    forecasts = get_latest_forecasts(db, asset_id)
    alerts = list_alerts_for_asset(db, asset_id, limit=10)

    pdf = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, y, f"ThesisLab Daily Report - {asset_id.upper()}")
    y -= 28

    pdf.setFont("Helvetica", 11)
    y = _draw_lines(
        pdf, 40, y,
        [
            f"Generated at: {datetime.now(timezone.utc).isoformat()}",
            f"Last price: {getattr(feature, 'last_price', 'n/a')}",
            f"Trend score: {getattr(feature, 'trend_score', 'n/a')}",
            f"Sentiment score: {getattr(feature, 'sentiment_score', 'n/a')}",
            f"Fragility score: {getattr(feature, 'fragility_score', 'n/a')}",
            f"Regime: {getattr(feature, 'regime_label', 'n/a')}",
            f"Dominant narrative: {getattr(feature, 'dominant_narrative', 'n/a')}",
        ],
    )
    y -= 10

    if thesis:
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(40, y, "Latest Thesis")
        y -= 18
        pdf.setFont("Helvetica", 10)
        y = _draw_lines(pdf, 40, y, [thesis.thesis[:500], "", "Anti-thesis:", thesis.anti_thesis[:300]], step=14)
        y -= 8

    if forecasts:
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(40, y, "Forecasts")
        y -= 18
        pdf.setFont("Helvetica", 10)
        lines = [
            f"{f.horizon}: direction={f.direction}, confidence={f.confidence:.2f}, expected_return_pct={f.expected_return_pct:.3f}"
            for f in forecasts
        ]
        y = _draw_lines(pdf, 40, y, lines, step=14)
        y -= 8

    if alerts:
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(40, y, "Recent Alerts")
        y -= 18
        pdf.setFont("Helvetica", 10)
        lines = [f"[{a.severity}] {a.title} - {a.message}" for a in alerts]
        y = _draw_lines(pdf, 40, y, lines, step=14)

    pdf.showPage()
    pdf.save()
    return str(file_path), file_name


def generate_watchlist_daily_report(db: Session, watchlist_id: int) -> tuple[str, str]:
    watchlist = get_watchlist(db, watchlist_id)
    assets = list_watchlist_assets(db, watchlist_id)
    out_dir = _ensure_reports_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_name = f"watchlist_report_{watchlist_id}_{ts}.pdf"
    file_path = out_dir / file_name

    pdf = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, y, f"Watchlist Daily Report - {watchlist.name if watchlist else watchlist_id}")
    y -= 28
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    y -= 24

    for asset_id in assets:
        feature = get_latest_feature_snapshot(db, asset_id)
        if y < 120:
            pdf.showPage()
            y = height - 50
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(40, y, asset_id.upper())
        y -= 16
        pdf.setFont("Helvetica", 10)
        lines = [
            f"Last price: {getattr(feature, 'last_price', 'n/a')}",
            f"Trend score: {getattr(feature, 'trend_score', 'n/a')}",
            f"Sentiment score: {getattr(feature, 'sentiment_score', 'n/a')}",
            f"Fragility score: {getattr(feature, 'fragility_score', 'n/a')}",
            f"Regime: {getattr(feature, 'regime_label', 'n/a')}",
        ]
        y = _draw_lines(pdf, 50, y, lines, step=13)
        y -= 12

    pdf.showPage()
    pdf.save()
    return str(file_path), file_name
