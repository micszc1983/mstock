"""Progi meta-modelu kalibrowane po kosztach osobno dla rynku i reżimu."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import MLModelRunORM


@dataclass(frozen=True)
class MetaThreshold:
    threshold: float
    scope: str
    sample_size: int
    selected_trades: int
    expected_net_return_pct: float
    uncertainty_pct: float


_CACHE_TTL_SECONDS = 300.0
_observation_cache: dict[int, tuple[float, list[dict]]] = {}
_threshold_cache: dict[tuple[int, str, str], tuple[float, MetaThreshold]] = {}


def invalidate_meta_threshold_cache(db: Session | None = None) -> None:
    """Czyści cache po treningu/promocji, żeby nowe holdouty działały od razu."""
    if db is None:
        _observation_cache.clear()
        _threshold_cache.clear()
        return
    bind_key = id(db.get_bind())
    _observation_cache.pop(bind_key, None)
    for key in [key for key in _threshold_cache if key[0] == bind_key]:
        _threshold_cache.pop(key, None)


def _observations(db: Session) -> list[dict]:
    bind_key = id(db.get_bind())
    cached = _observation_cache.get(bind_key)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    rows = db.scalars(select(MLModelRunORM).where(
        MLModelRunORM.target_name == "target_meta_label",
        MLModelRunORM.is_active.is_(True),
        MLModelRunORM.deployment_role == "champion",
    )).all()
    result = []
    for row in rows:
        try:
            metrics = json.loads(row.metrics_json)
            result.extend(metrics.get("meta_holdout_observations") or [])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    _observation_cache[bind_key] = (now, result)
    return result


def _fit(observations: list[dict], scope: str) -> MetaThreshold | None:
    if len(observations) < 30:
        return None
    best = None
    for step in range(13):
        threshold = 0.50 + step * 0.025
        selected = [float(row["net_return_pct"]) for row in observations if float(row["probability"]) >= threshold]
        if len(selected) < max(20, int(len(observations) * 0.08)):
            continue
        average = mean(selected)
        uncertainty = (pstdev(selected) / math.sqrt(len(selected))) if len(selected) > 1 else 999.0
        # Przewaga musi przetrwać koszt i błąd estymacji; lekka kara ogranicza
        # progi wybierające tylko kilka ekstremalnych obserwacji.
        utility = average - uncertainty - 0.05 * (1.0 - len(selected) / len(observations))
        candidate = (utility, threshold, selected, average, uncertainty)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None or best[0] <= 0:
        return None
    _, threshold, selected, average, uncertainty = best
    return MetaThreshold(
        threshold=round(threshold, 4), scope=scope, sample_size=len(observations),
        selected_trades=len(selected), expected_net_return_pct=round(average, 6),
        uncertainty_pct=round(uncertainty, 6),
    )


def calibrated_meta_threshold(db: Session, market: str, regime: str) -> MetaThreshold:
    cache_key = (id(db.get_bind()), market, regime)
    cached = _threshold_cache.get(cache_key)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    observations = _observations(db)
    candidates = (
        ([row for row in observations if row.get("market") == market and row.get("regime") == regime], "market_regime"),
        ([row for row in observations if row.get("market") == market], "market"),
        (observations, "global"),
    )
    minimum = {"market_regime": 60, "market": 100, "global": 150}
    for rows, scope in candidates:
        if len(rows) >= minimum[scope]:
            fitted = _fit(rows, scope)
            if fitted is not None:
                _threshold_cache[cache_key] = (now, fitted)
                return fitted
    fallback = MetaThreshold(
        threshold=settings.meta_trade_probability_threshold,
        scope="configured_fallback", sample_size=0, selected_trades=0,
        expected_net_return_pct=0.0, uncertainty_pct=0.0,
    )
    _threshold_cache[cache_key] = (now, fallback)
    return fallback
