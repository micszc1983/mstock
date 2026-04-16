from __future__ import annotations

import math
from datetime import datetime, timezone

from app.schemas.features import DailyAssetFeatureSnapshot, ForecastResponse
from app.core.config import weights as W


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def build_forecasts(snapshot: DailyAssetFeatureSnapshot) -> list[ForecastResponse]:
    generated_at = datetime.now(timezone.utc)
    base_signal = (
        W.FORECAST_TREND_W * (snapshot.trend_score / 100.0)
        + W.FORECAST_SENTIMENT_W * (snapshot.sentiment_score / 100.0)
        + W.FORECAST_MOMENTUM_W * (snapshot.momentum_20d / 20.0)
        - W.FORECAST_DIVERGENCE_PENALTY * (snapshot.divergence_score / 100.0)
        - W.FORECAST_FRAGILITY_PENALTY * (snapshot.fragility_score / 100.0)
    )
    vol_penalty = min(snapshot.volatility_10d / 10.0, 0.35)

    configs = {
        "1d": {"scale": 1.2, "range_mult": 0.8},
        "5d": {"scale": 1.6, "range_mult": 1.5},
        "20d": {"scale": 2.2, "range_mult": 2.4},
    }

    outputs: list[ForecastResponse] = []
    for horizon, cfg in configs.items():
        horizon_signal = base_signal * cfg["scale"] - vol_penalty
        up_probability = _sigmoid(horizon_signal)
        down_probability = 1.0 - up_probability
        direction = "up" if up_probability >= 0.5 else "down"
        confidence = abs(up_probability - 0.5) * 2.0
        expected_return_pct = horizon_signal * W.FORECAST_RETURN_SCALE
        range_width = max(snapshot.volatility_10d * cfg["range_mult"], 0.25)
        expected_range_low = snapshot.last_price * (1.0 + ((expected_return_pct - range_width) / 100.0))
        expected_range_high = snapshot.last_price * (1.0 + ((expected_return_pct + range_width) / 100.0))

        outputs.append(
            ForecastResponse(
                asset_id=snapshot.asset_id,
                horizon=horizon,
                generated_at=generated_at,
                direction=direction,
                up_probability=round(up_probability, 4),
                down_probability=round(down_probability, 4),
                confidence=round(confidence, 4),
                expected_return_pct=round(expected_return_pct, 4),
                expected_range_low=round(expected_range_low, 4),
                expected_range_high=round(expected_range_high, 4),
                model_name="heuristic_v1",
                regime_label=snapshot.regime_label,
            )
        )

    return outputs
