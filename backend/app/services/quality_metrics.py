from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy.orm import Session

from app.db.models import ForecastORM
from app.repositories.forecasts import list_forecast_history
from app.repositories.outcomes import list_outcomes_for_asset
from app.schemas.quality import (
    ForecastQualitySummary,
    ThesisQualityByHorizon,
    ThesisQualitySummary,
)


def _safe_mean(values: list[float]) -> float:
    return round(mean(values), 4) if values else 0.0


def build_thesis_quality_summary(db: Session, asset_id: str, limit: int = 500) -> ThesisQualitySummary:
    outcomes = list_outcomes_for_asset(db, asset_id, limit=limit)
    total = len(outcomes)
    if total == 0:
        return ThesisQualitySummary(
            asset_id=asset_id,
            total_outcomes=0,
            directional_accuracy=0.0,
            average_realized_return_pct=0.0,
            bullish_win_rate=0.0,
            bearish_win_rate=0.0,
            flat_rate=0.0,
        )

    directional_accuracy = sum(1 for row in outcomes if row.was_directionally_correct) / total
    bullish = sum(1 for row in outcomes if row.outcome_label == "bullish_win") / total
    bearish = sum(1 for row in outcomes if row.outcome_label == "bearish_win") / total
    flat = sum(1 for row in outcomes if row.outcome_label == "flat") / total

    return ThesisQualitySummary(
        asset_id=asset_id,
        total_outcomes=total,
        directional_accuracy=round(directional_accuracy, 4),
        average_realized_return_pct=_safe_mean([row.realized_return_pct for row in outcomes]),
        bullish_win_rate=round(bullish, 4),
        bearish_win_rate=round(bearish, 4),
        flat_rate=round(flat, 4),
    )


def build_thesis_quality_by_horizon(db: Session, asset_id: str, limit: int = 500) -> list[ThesisQualityByHorizon]:
    outcomes = list_outcomes_for_asset(db, asset_id, limit=limit)
    buckets = defaultdict(list)
    for row in outcomes:
        buckets[row.horizon].append(row)

    results: list[ThesisQualityByHorizon] = []
    for horizon, rows in sorted(buckets.items()):
        total = len(rows)
        directional_accuracy = sum(1 for row in rows if row.was_directionally_correct) / total if total else 0.0
        bullish = sum(1 for row in rows if row.outcome_label == "bullish_win") / total if total else 0.0
        bearish = sum(1 for row in rows if row.outcome_label == "bearish_win") / total if total else 0.0
        flat = sum(1 for row in rows if row.outcome_label == "flat") / total if total else 0.0

        results.append(
            ThesisQualityByHorizon(
                asset_id=asset_id,
                horizon=horizon,
                total_outcomes=total,
                directional_accuracy=round(directional_accuracy, 4),
                average_realized_return_pct=_safe_mean([row.realized_return_pct for row in rows]),
                bullish_win_rate=round(bullish, 4),
                bearish_win_rate=round(bearish, 4),
                flat_rate=round(flat, 4),
            )
        )
    return results


def build_forecast_quality_summary(db: Session, asset_id: str, limit: int = 500) -> list[ForecastQualitySummary]:
    forecasts = list_forecast_history(db, asset_id, limit=limit)
    buckets = defaultdict(list)
    for row in forecasts:
        buckets[row.horizon].append(row)

    results: list[ForecastQualitySummary] = []
    for horizon, rows in sorted(buckets.items()):
        results.append(
            ForecastQualitySummary(
                asset_id=asset_id,
                horizon=horizon,
                total_forecasts=len(rows),
                average_up_probability=_safe_mean([row.up_probability for row in rows]),
                average_down_probability=_safe_mean([row.down_probability for row in rows]),
                average_confidence=_safe_mean([row.confidence for row in rows]),
                average_expected_return_pct=_safe_mean([row.expected_return_pct for row in rows]),
            )
        )
    return results
