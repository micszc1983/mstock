from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import AssetORM, PortfolioPositionORM
from app.db.session import Base
from app.services.recommendation_calibration import (
    _cached_fit,
    _calibration_session,
    _tune_threshold,
    invalidate_calibration_cache,
    market_segment,
)
from app.services.recommendation_engine import build_recommendation
from app.services.recommendation_engine import _forecast_consensus_veto


def test_market_calibration_segments_gpw_usa_and_other():
    gpw = AssetORM(id="gpw", symbol="PKO", name="PKO", type="stock", currency="PLN", price_symbol="PKO.WA")
    usa = AssetORM(id="usa", symbol="NVDA", name="NVIDIA", type="stock", currency="USD", price_symbol="NVDA")
    metal = AssetORM(id="gold-test", symbol="GOLD", name="Gold", type="metal", currency="USD")

    assert market_segment(gpw) == "GPW"
    assert market_segment(usa) == "USA"
    assert market_segment(metal) == "OTHER"


def test_threshold_requires_edge_above_cost_and_uncertainty():
    probabilities = np.linspace(0.45, 0.95, 120)
    profitable_returns = np.where(probabilities >= 0.65, 2.0, -0.3)
    costs = np.full(120, 0.4)

    result = _tune_threshold(probabilities, profitable_returns, costs, direction=1)

    assert result.threshold <= 0.8
    assert result.selected >= 10
    assert result.expected_net_pct > result.uncertainty_pct


def test_threshold_disables_trade_when_cost_consumes_edge():
    probabilities = np.linspace(0.4, 0.95, 120)
    returns = np.full(120, 0.15)
    costs = np.full(120, 0.4)

    result = _tune_threshold(probabilities, returns, costs, direction=1)

    assert result.threshold > 1.0
    assert result.selected == 0


def test_calibration_session_uses_local_market_date():
    moment = datetime(2026, 7, 24, 22, 30, tzinfo=timezone.utc)

    assert _calibration_session("GPW", moment) == "2026-07-25"
    assert _calibration_session("USA", moment) == "2026-07-24"


def test_calibration_cache_stays_frozen_until_next_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'frozen-calibration.db'}")
    calls = []
    current_session = ["2026-07-24"]
    sentinel = object()
    monkeypatch.setattr(
        "app.services.recommendation_calibration._calibration_session",
        lambda _market, at=None: current_session[0],
    )
    monkeypatch.setattr(
        "app.services.recommendation_calibration._fit_segment",
        lambda *_args, **_kwargs: calls.append(current_session[0]) or sentinel,
    )
    invalidate_calibration_cache(force=True)
    with Session(engine) as db:
        assert _cached_fit(db, "GPW", "range_bound", "market_regime") is sentinel
        assert _cached_fit(db, "GPW", "range_bound", "market_regime") is sentinel
        invalidate_calibration_cache()
        assert _cached_fit(db, "GPW", "range_bound", "market_regime") is sentinel
        assert calls == ["2026-07-24"]

        current_session[0] = "2026-07-25"
        invalidate_calibration_cache()
        assert _cached_fit(db, "GPW", "range_bound", "market_regime") is sentinel
        assert calls == ["2026-07-24", "2026-07-25"]
    invalidate_calibration_cache(force=True)


def test_strong_three_horizon_disagreement_vetoes_calibrated_trade(monkeypatch):
    monkeypatch.setattr(
        "app.services.recommendation_engine.settings."
        "recommendation_forecast_consensus_veto_probability",
        0.45,
    )

    bearish = [
        SimpleNamespace(direction="down", up_probability=probability)
        for probability in (0.35, 0.32, 0.28)
    ]
    bullish = [
        SimpleNamespace(direction="up", up_probability=probability)
        for probability in (0.65, 0.68, 0.72)
    ]

    assert "KUP" in (_forecast_consensus_veto("KUP", *bearish) or "")
    assert "SPRZEDAJ" in (_forecast_consensus_veto("SPRZEDAJ", *bullish) or "")
    assert _forecast_consensus_veto(
        "KUP",
        bearish[0],
        SimpleNamespace(direction="up", up_probability=0.52),
        bearish[2],
    ) is None
    assert _forecast_consensus_veto(
        "KUP",
        bearish[0],
        SimpleNamespace(direction="down", up_probability=0.46),
        bearish[2],
    ) is None


def test_no_data_means_no_trade_unless_position_is_owned(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'recommendations.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.commit()

        flat = build_recommendation(db, "abc")
        assert flat is not None
        assert flat.recommendation == "BRAK TRANSAKCJI"

        db.add(PortfolioPositionORM(
            asset_id="abc", quantity=5, avg_buy_price=100,
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
        held = build_recommendation(db, "abc")
        assert held is not None
        assert held.recommendation == "TRZYMAJ"
