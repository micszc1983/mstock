from __future__ import annotations

import sys
import smtplib
import io
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    _WA = ZoneInfo("Europe/Warsaw")
except ImportError:
    import pytz as _pytz  # type: ignore
    _WA = _pytz.timezone("Europe/Warsaw")
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

from sqlalchemy.orm import Session

sys.path.insert(0, "/home/tt38dn/.local/lib/python3.13/site-packages")

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.core.config import settings
from app.repositories.assets import get_asset
from app.repositories.portfolio_positions import list_positions
from app.repositories.prices import list_prices
from app.services.currency_service import to_pln

# ── Rejestracja czcionek z polskimi znakami ───────────────────────────────────
_FONTS_DIR = "/usr/share/fonts/truetype/dejavu"
_fonts_registered = False

def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont("DejaVu",         f"{_FONTS_DIR}/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold",    f"{_FONTS_DIR}/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuMono",     f"{_FONTS_DIR}/DejaVuSansMono.ttf"))
    _fonts_registered = True

# ── Kolory ────────────────────────────────────────────────────────────────────
GREEN  = colors.HexColor("#16a34a")
RED    = colors.HexColor("#dc2626")
ORANGE = colors.HexColor("#d97706")
GRAY   = colors.HexColor("#64748b")
DARK   = colors.HexColor("#0f172a")
LIGHT  = colors.HexColor("#f1f5f9")
HEADER = colors.HexColor("#1e3a5f")
WHITE  = colors.white


def build_portfolio_pdf(db: Session, recommendations: dict) -> bytes:
    _register_fonts()
    positions = [p for p in list_positions(db) if p.quantity > 0]
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )

    # ── Style ─────────────────────────────────────────────────────────────────
    title_st = ParagraphStyle("T", fontName="DejaVu-Bold",  fontSize=18, textColor=HEADER, spaceAfter=2)
    sub_st   = ParagraphStyle("S", fontName="DejaVu",       fontSize=9,  textColor=GRAY,   spaceAfter=10)
    note_st  = ParagraphStyle("N", fontName="DejaVu",       fontSize=7.5, textColor=GRAY,  leading=11)
    sum_key  = ParagraphStyle("K", fontName="DejaVu-Bold",  fontSize=9,  textColor=DARK)
    sum_val  = ParagraphStyle("V", fontName="DejaVu",       fontSize=9,  textColor=DARK)

    now = datetime.now(_WA).strftime("%d.%m.%Y %H:%M")
    story = []

    # ── Nagłówek ──────────────────────────────────────────────────────────────
    story.append(Paragraph("MStock — Raport Portfela", title_st))
    story.append(Paragraph(f"Wygenerowano: {now} (czas warszawski)", sub_st))
    story.append(HRFlowable(width="100%", thickness=1.2, color=HEADER, spaceAfter=10))

    # ── Buduj wiersze danych ──────────────────────────────────────────────────
    rows_buy, rows_sell, rows_hold = [], [], []
    total_by_currency: dict[str, float] = {}

    # Indeksy: 0=Spółka, 1=Symbol, 2=Ilość, 3=Zakup, 4=Cena, 5=Wartość, 6=Zysk%, 7=Rekomendacja, 8=ML, 9=5d, 10=20d
    COL_W = [5.5*cm, 1.7*cm, 1.6*cm, 2.5*cm, 2.5*cm, 2.5*cm, 1.7*cm, 2.8*cm, 1.3*cm, 1.3*cm, 1.3*cm]
    HEADER_ROW = ["Spółka", "Symbol", "Ilość",
                  "Zakup", "Cena bież.", "Wartość",
                  "Zysk %", "Rekomendacja", "ML", "5d", "20d"]

    def dir_arrow(d: str | None) -> str:
        if d == "up":   return "▲"
        if d == "down": return "▼"
        return "—"

    def build_row(pos, asset, rd: dict):
        source_last = 0.0
        prices = list_prices(db, pos.asset_id, limit=1)
        if prices:
            source_last = float(prices[-1].close)
        elif rd.get("last_price"):
            source_last = float(rd["last_price"])
        source_currency = asset.currency if asset else rd.get("currency", "PLN")
        try:
            last = float(to_pln(source_last, source_currency) or 0.0)
        except ValueError:
            last = 0.0
        curr  = "PLN"
        rec   = rd.get("recommendation")
        ml    = rd.get("ml_prediction")
        f5    = rd.get("forecast_dir_5d")
        f20   = rd.get("forecast_dir_20d")
        val   = pos.quantity * last
        avg   = pos.avg_buy_price
        if avg is not None and pos.cost_currency != "PLN" and source_currency != "PLN":
            try:
                avg = to_pln(avg, source_currency, pos.purchase_date)
            except ValueError:
                avg = None
        if avg and last and avg > 0:
            pl_pct = (last - avg) / avg * 100.0
            pl_str = f"{pl_pct:+.1f}%"
        else:
            pl_pct = None
            pl_str = "—"
        row = [
            (asset.name[:32] if asset else pos.asset_id),
            (asset.symbol if asset else pos.asset_id.upper()),
            f"{pos.quantity:g}",
            f"{avg:.2f} {curr}" if avg else "—",
            f"{last:.2f} {curr}" if last else "—",
            f"{val:,.0f} {curr}" if last else "—",
            pl_str,
            rec or "—",
            dir_arrow(ml if ml in ("up", "down") else None),
            dir_arrow(f5),
            dir_arrow(f20),
        ]
        return row, rec, val, pl_pct

    for pos in positions:
        asset = get_asset(db, pos.asset_id)
        rd    = recommendations.get(pos.asset_id, {})
        row, rec, val, pl_pct = build_row(pos, asset, rd)
        curr = "PLN"
        if val:
            total_by_currency[curr] = total_by_currency.get(curr, 0) + val
        if rec == "KUP":
            rows_buy.append((row, pos.asset_id, pl_pct))
        elif rec == "SPRZEDAJ":
            rows_sell.append((row, pos.asset_id, pl_pct))
        else:
            rows_hold.append((row, pos.asset_id, pl_pct))

    # ── Buduj tabelę sekcji ───────────────────────────────────────────────────
    def table_for(data_with_ids, rec_col_color: colors.Color) -> Table:
        rows = [HEADER_ROW] + [r for r, _, _ in data_with_ids]
        t = Table(rows, colWidths=COL_W, repeatRows=1)
        style = TableStyle([
            # Nagłówek
            ("BACKGROUND",    (0, 0), (-1, 0), HEADER),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "DejaVu-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 8),
            ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
            # Dane
            ("FONTNAME",      (0, 1), (-1, -1), "DejaVu"),
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [LIGHT, WHITE]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            # Wyrównanie
            ("ALIGN",         (2, 1), (6, -1),  "RIGHT"),   # Ilość … Zysk%
            ("ALIGN",         (0, 1), (1, -1),  "LEFT"),    # Spółka, Symbol
            ("ALIGN",         (7, 1), (7, -1),  "CENTER"),  # Rekomendacja
            ("ALIGN",         (8, 1), (10, -1), "CENTER"),  # ML, 5d, 20d
        ])
        for i, (row, _, pl_pct) in enumerate(data_with_ids, start=1):
            # Zysk% — col 6
            if pl_pct is not None:
                pl_color = GREEN if pl_pct > 0 else (RED if pl_pct < 0 else GRAY)
                style.add("TEXTCOLOR", (6, i), (6, i), pl_color)
                style.add("FONTNAME",  (6, i), (6, i), "DejaVu-Bold")
            # Rekomendacja — col 7
            rec_val = row[7]
            rc = GREEN if rec_val == "KUP" else RED if rec_val == "SPRZEDAJ" else ORANGE
            style.add("TEXTCOLOR", (7, i), (7, i), rc)
            style.add("FONTNAME",  (7, i), (7, i), "DejaVu-Bold")
            # Strzałki ML, 5d, 20d — cols 8, 9, 10
            for ci in (8, 9, 10):
                arrow = row[ci]
                ac = GREEN if arrow == "▲" else (RED if arrow == "▼" else GRAY)
                style.add("TEXTCOLOR", (ci, i), (ci, i), ac)
                style.add("FONTNAME",  (ci, i), (ci, i), "DejaVu-Bold")
        t.setStyle(style)
        return t

    # ── Sekcje ────────────────────────────────────────────────────────────────
    if rows_sell:
        story.append(Paragraph(
            "● Do sprzedaży (SPRZEDAJ)",
            ParagraphStyle("rs", fontName="DejaVu-Bold", fontSize=10, textColor=RED, spaceBefore=8, spaceAfter=3)
        ))
        story.append(table_for(rows_sell, RED))

    if rows_buy:
        story.append(Paragraph(
            "● Do kupna (KUP)",
            ParagraphStyle("rb", fontName="DejaVu-Bold", fontSize=10, textColor=GREEN, spaceBefore=10, spaceAfter=3)
        ))
        story.append(table_for(rows_buy, GREEN))

    if rows_hold:
        story.append(Paragraph(
            "● Trzymaj / brak danych",
            ParagraphStyle("rh", fontName="DejaVu-Bold", fontSize=10, textColor=ORANGE, spaceBefore=10, spaceAfter=3)
        ))
        story.append(table_for(rows_hold, ORANGE))

    # ── Podsumowanie ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=HEADER, spaceBefore=4, spaceAfter=6))

    totals_str = "   ".join(f"{v:,.0f} {c}" for c, v in sorted(total_by_currency.items()))
    summary_rows = [
        [Paragraph("Liczba pozycji:", sum_key),          Paragraph(str(len(positions)), sum_val)],
        [Paragraph("Wartość portfela:", sum_key), Paragraph(totals_str or "—", sum_val)],
        [Paragraph("Do kupna:", sum_key),                Paragraph(str(len(rows_buy)), sum_val)],
        [Paragraph("Do sprzedaży:", sum_key),       Paragraph(str(len(rows_sell)), sum_val)],
        [Paragraph("Trzymaj:", sum_key),                 Paragraph(str(len(rows_hold)), sum_val)],
    ]
    sum_t = Table(summary_rows, colWidths=[4.5*cm, 14*cm])
    sum_t.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
    ]))
    story.append(sum_t)

    # ── Stopka ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "Raport wygenerowany automatycznie przez MStock. Nie stanowi porady inwestycyjnej. "
        "Decyzje inwestycyjne podejmujesz na własną odpowiedzialność.",
        note_st,
    ))

    doc.build(story)
    return buf.getvalue()


def send_portfolio_report(db: Session, recommendations: dict, to_email: str = "dev@coad.pl") -> dict:
    if not settings.smtp_host or not settings.smtp_username:
        return {"ok": False, "detail": "SMTP nie skonfigurowane w .env (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL)"}

    try:
        pdf_bytes = build_portfolio_pdf(db, recommendations)
    except Exception as e:
        return {"ok": False, "detail": f"Błąd generowania PDF: {e}"}

    now_str  = datetime.now(_WA).strftime("%d.%m.%Y %H:%M")
    filename = f"mstock_portfel_{datetime.now(_WA).strftime('%Y%m%d')}.pdf"

    msg = MIMEMultipart()
    msg["From"]    = settings.smtp_from_email or settings.smtp_username
    msg["To"]      = to_email
    msg["Subject"] = f"MStock — Raport portfela {now_str}"

    body = (
        f"Cześć,\n\n"
        f"w załączniku znajdziesz dzienny raport portfela MStock z dnia {now_str} (czas warszawski).\n\n"
        f"Raport zawiera:\n"
        f" • Wszystkie pozycje z aktualną wycąeną\n"
        f" • Cenę zakupu i Zysk/Stratę %\n"
        f" • Rekomendacje: KUP / SPRZEDAJ / TRZYMAJ\n"
        f" • Predykcje ML (5d, 20d)\n\n"
        f"Pozdrawiam,\nMStock\n"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    try:
        if settings.smtp_port == 465:
            import ssl as _ssl
            ctx = _ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx) as server:
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        return {"ok": True, "detail": f"Email wysłany na {to_email}", "filename": filename}
    except Exception as e:
        return {"ok": False, "detail": f"Błąd SMTP: {e}"}
