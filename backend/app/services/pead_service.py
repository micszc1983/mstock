from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EarningsORM, PricePointORM


def _close_on_date(db: Session, asset_id: str, target: date) -> float | None:
    """Return closing price on target date or up to 4 days forward (skip weekends/holidays)."""
    for offset in range(5):
        d = target + timedelta(days=offset)
        dt_from = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        dt_to = dt_from + timedelta(days=1)
        row = db.scalar(
            select(PricePointORM)
            .where(
                PricePointORM.asset_id == asset_id,
                PricePointORM.timestamp >= dt_from,
                PricePointORM.timestamp < dt_to,
            )
            .limit(1)
        )
        if row is not None:
            return row.close
    return None


def _trading_days(start: date, end: date) -> int:
    count = 0
    d = start
    while d < end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def analyze_pead(db: Session, asset_id: str) -> dict:
    past = db.scalars(
        select(EarningsORM)
        .where(
            EarningsORM.asset_id == asset_id,
            EarningsORM.eps_actual.isnot(None),
            EarningsORM.eps_surprise_pct.isnot(None),
        )
        .order_by(EarningsORM.report_date.desc())
        .limit(12)
    ).all()

    if not past:
        return {
            "asset_id": asset_id,
            "status": "no_data",
            "status_description": "Brak danych wynikowych",
            "reliability_pct": None,
            "n_events": 0,
            "events": [],
            "current_drift_pct": None,
            "days_since_earnings": None,
            "last_report_date": None,
            "last_surprise_label": None,
            "last_eps_surprise_pct": None,
            "sue": None,
        }

    surprises = [e.eps_surprise_pct for e in past if e.eps_surprise_pct is not None]
    sue = None
    if len(surprises) >= 3:
        std = statistics.stdev(surprises)
        if std > 0:
            sue = round(surprises[0] / std, 2)
        else:
            sue = round(surprises[0], 2)

    events = []
    aligned_count = 0
    total_with_drift = 0

    for e in past:
        base = _close_on_date(db, asset_id, e.report_date)
        c1  = _close_on_date(db, asset_id, e.report_date + timedelta(days=1))
        c5  = _close_on_date(db, asset_id, e.report_date + timedelta(days=5))
        c20 = _close_on_date(db, asset_id, e.report_date + timedelta(days=20))

        d1  = round((c1  / base - 1) * 100, 2) if base and c1  else None
        d5  = round((c5  / base - 1) * 100, 2) if base and c5  else None
        d20 = round((c20 / base - 1) * 100, 2) if base and c20 else None

        aligned: bool | None = None
        if e.surprise_label in ("BEAT", "MISS") and d5 is not None:
            total_with_drift += 1
            if (e.surprise_label == "BEAT" and d5 > 0) or (e.surprise_label == "MISS" and d5 < 0):
                aligned = True
                aligned_count += 1
            else:
                aligned = False

        events.append({
            "report_date": e.report_date.isoformat(),
            "fiscal_period": e.fiscal_period,
            "eps_surprise_pct": e.eps_surprise_pct,
            "surprise_label": e.surprise_label,
            "drift_1d": d1,
            "drift_5d": d5,
            "drift_20d": d20,
            "aligned": aligned,
        })

    reliability_pct = round(aligned_count / total_with_drift * 100, 1) if total_with_drift > 0 else None

    most_recent = past[0]
    today = date.today()
    days_since = _trading_days(most_recent.report_date, today)

    current_drift_pct = None
    base = _close_on_date(db, asset_id, most_recent.report_date)
    recent_close = _close_on_date(db, asset_id, today - timedelta(days=1))
    if base and recent_close:
        current_drift_pct = round((recent_close / base - 1) * 100, 2)

    if days_since <= 20:
        days_left = max(0, 20 - days_since)
        status = "active"
        lbl = most_recent.surprise_label or "?"
        status_description = f"Drift aktywny: {days_since}d po {lbl} ({days_left}d pozostało w oknie)"
    else:
        status = "expired"
        status_description = f"Okno PEAD wygasło — {days_since}d po ostatnim raporcie"

    return {
        "asset_id": asset_id,
        "status": status,
        "status_description": status_description,
        "reliability_pct": reliability_pct,
        "n_events": len(events),
        "events": events,
        "current_drift_pct": current_drift_pct,
        "days_since_earnings": days_since,
        "last_report_date": most_recent.report_date.isoformat(),
        "last_surprise_label": most_recent.surprise_label,
        "last_eps_surprise_pct": most_recent.eps_surprise_pct,
        "sue": sue,
    }