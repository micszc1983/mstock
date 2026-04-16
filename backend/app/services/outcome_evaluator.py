from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.utils.datetime import ensure_utc

from app.db.models import ThesisORM
from app.mappers import price_to_schema
from app.repositories.outcomes import delete_outcomes_for_thesis, insert_outcome
from app.repositories.prices import list_prices
from app.repositories.theses import list_thesis_history


HORIZON_TO_DAYS = {
    "1d": 1,
    "5d": 5,
    "20d": 20,
}


def _direction_from_text(thesis_text: str, anti_thesis_text: str) -> str:
    text = f"{thesis_text} {anti_thesis_text}".lower()
    bullish_terms = ["wzrost", "wzrostową", "bullish", "dodatni", "supported", "spójny układ techniczny"]
    bearish_terms = ["spadek", "bearish", "negatywny", "słaby", "mniej trwały", "podważony"]
    bull_hits = sum(1 for t in bullish_terms if t in text)
    bear_hits = sum(1 for t in bearish_terms if t in text)
    if bull_hits >= bear_hits:
        return "up"
    return "down"


def _find_realized_price(prices, base_timestamp, days: int):
    eligible = [p for p in prices if ensure_utc(p.timestamp) > ensure_utc(base_timestamp)]
    if len(eligible) < days:
        return None, None
    point = eligible[days - 1]
    return point.timestamp, point.close


def evaluate_thesis_outcomes(db: Session, thesis_row: ThesisORM) -> int:
    prices = [price_to_schema(row) for row in list_prices(db, thesis_row.asset_id)]
    base_candidates = [p for p in prices if ensure_utc(p.timestamp) == ensure_utc(thesis_row.source_snapshot_at)]
    if not base_candidates:
        base_candidates = [p for p in prices if ensure_utc(p.timestamp) <= ensure_utc(thesis_row.source_snapshot_at)]
    if not base_candidates:
        return 0

    base_price = base_candidates[-1].close
    expected_direction = _direction_from_text(thesis_row.thesis, thesis_row.anti_thesis)

    delete_outcomes_for_thesis(db, thesis_row.id)
    created = 0

    for horizon, days in HORIZON_TO_DAYS.items():
        evaluated_at, realized_price = _find_realized_price(prices, thesis_row.source_snapshot_at, days)
        if realized_price is None or evaluated_at is None:
            continue

        realized_return_pct = ((realized_price - base_price) / base_price) * 100.0 if base_price else 0.0
        was_directionally_correct = realized_return_pct >= 0 if expected_direction == "up" else realized_return_pct < 0

        if realized_return_pct > 1.0:
            label = "bullish_win"
        elif realized_return_pct < -1.0:
            label = "bearish_win"
        else:
            label = "flat"

        insert_outcome(
            db=db,
            thesis_id=thesis_row.id,
            asset_id=thesis_row.asset_id,
            evaluated_at=evaluated_at,
            horizon=horizon,
            base_price=base_price,
            realized_price=realized_price,
            realized_return_pct=round(realized_return_pct, 4),
            was_directionally_correct=was_directionally_correct,
            outcome_label=label,
        )
        created += 1

    db.commit()
    return created


def evaluate_asset_outcomes(db: Session, asset_id: str, limit: int = 100) -> int:
    created = 0
    for thesis_row in list_thesis_history(db, asset_id, limit=limit):
        created += evaluate_thesis_outcomes(db, thesis_row)
    return created
