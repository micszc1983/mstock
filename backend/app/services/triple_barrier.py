"""Point-in-time triple barrier i etykieta meta „wykonać / odpuścić”."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev


@dataclass(frozen=True)
class TripleBarrierOutcome:
    direction_label: int
    meta_label: int
    hit: str
    raw_return_pct: float
    side: int
    strategy_net_return_pct: float
    take_profit_pct: float
    stop_loss_pct: float


def primary_side(features: dict) -> int:
    """Kierunek bazowy wykorzystuje tylko cechy znane w chwili decyzji."""
    def value(name: str) -> float:
        try:
            result = float(features.get(name, 0.0) or 0.0)
            return result if math.isfinite(result) else 0.0
        except (TypeError, ValueError):
            return 0.0

    score = (
        max(-1.0, min(1.0, value("trend_score") / 100.0)) * 0.45
        + max(-1.0, min(1.0, value("momentum_20d") / 15.0)) * 0.35
        + max(-1.0, min(1.0, value("sentiment_score") / 100.0)) * 0.20
    )
    return 1 if score >= 0 else -1


def build_triple_barrier_outcome(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    index: int,
    *,
    side: int,
    transaction_cost_pct: float,
    horizon_sessions: int = 10,
    take_profit_vol_multiplier: float = 1.25,
    stop_loss_vol_multiplier: float = 0.90,
) -> TripleBarrierOutcome | None:
    if index < 20 or index + horizon_sessions >= len(closes):
        return None
    base = float(closes[index])
    if base <= 0:
        return None
    trailing_returns = [
        (closes[pos] / closes[pos - 1] - 1.0) * 100.0
        for pos in range(index - 19, index + 1)
        if closes[pos - 1] > 0
    ]
    daily_volatility = pstdev(trailing_returns) if len(trailing_returns) >= 2 else 0.0
    # Bariery reagują na zmienność, ale zawsze pokrywają koszt i minimalny ruch.
    take_profit = max(
        transaction_cost_pct + 0.30,
        daily_volatility * math.sqrt(5.0) * take_profit_vol_multiplier,
        0.80,
    )
    stop_loss = max(
        transaction_cost_pct + 0.30,
        daily_volatility * math.sqrt(5.0) * stop_loss_vol_multiplier,
        0.60,
    )
    upper = base * (1.0 + take_profit / 100.0)
    lower = base * (1.0 - stop_loss / 100.0)

    hit = "vertical"
    raw_return = (closes[index + horizon_sessions] / base - 1.0) * 100.0
    for pos in range(index + 1, index + horizon_sessions + 1):
        upper_hit = highs[pos] >= upper
        lower_hit = lows[pos] <= lower
        if upper_hit and lower_hit:
            # Brak kolejności intraday: nie wolno optymistycznie wybierać TP.
            hit = "ambiguous"
            raw_return = -stop_loss if side > 0 else take_profit
            break
        if upper_hit:
            hit, raw_return = "upper", take_profit
            break
        if lower_hit:
            hit, raw_return = "lower", -stop_loss
            break

    direction = 1 if raw_return > 0 else 0
    net = side * raw_return - transaction_cost_pct
    meta = int(net > 0 and hit != "ambiguous")
    return TripleBarrierOutcome(
        direction_label=direction,
        meta_label=meta,
        hit=hit,
        raw_return_pct=round(raw_return, 6),
        side=1 if side >= 0 else -1,
        strategy_net_return_pct=round(net, 6),
        take_profit_pct=round(take_profit, 6),
        stop_loss_pct=round(stop_loss, 6),
    )
