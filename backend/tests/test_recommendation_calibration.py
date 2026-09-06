from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import AssetORM, PortfolioPositionORM
from app.db.session import Base
from app.services.recommendation_calibration import (
    BUY_CLASS,
    FEATURE_NAMES,
    NO_TRADE_CLASS,
    SELL_CLASS,
    ThresholdStats,
    _cached_fit,
    _calibration_session,
    _decision_from_finalized_record,
    _select_calibrated_action,
    _tune_threshold,
    _vector,
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


def test_threshold_disables_trade_when_probabilities_collapse_to_one_plateau():
    probabilities = np.full(200, 0.876)
    returns = np.tile([2.0, -1.0], 100)
    costs = np.full(200, 0.4)

    result = _tune_threshold(probabilities, returns, costs, direction=SELL_CLASS)

    assert result.threshold > 1.0
    assert result.selected == 0


def _profitable_threshold(threshold: float) -> ThresholdStats:
    return ThresholdStats(
        threshold=threshold,
        selected=100,
        expected_gross_pct=2.0,
        expected_net_pct=1.8,
        uncertainty_pct=0.4,
    )


def test_sell_is_rejected_when_buy_probability_is_higher():
    action = _select_calibrated_action(
        p_sell=0.42,
        p_no_trade=0.02,
        p_buy=0.56,
        buy=_profitable_threshold(0.75),
        sell=_profitable_threshold(0.40),
    )

    assert action == NO_TRADE_CLASS


def test_trade_requires_threshold_edge_and_highest_probability():
    buy = _profitable_threshold(0.60)
    sell = _profitable_threshold(0.55)

    assert _select_calibrated_action(0.20, 0.15, 0.65, buy, sell) == BUY_CLASS
    assert _select_calibrated_action(0.60, 0.10, 0.30, buy, sell) == SELL_CLASS
    assert _select_calibrated_action(
        0.25, 0.45, 0.30, _profitable_threshold(0.25), sell
    ) == NO_TRADE_CLASS
    assert _select_calibrated_action(
        0.45, 0.10, 0.45, _profitable_threshold(0.40), _profitable_threshold(0.40)
    ) == NO_TRADE_CLASS


def test_calibration_session_uses_local_market_date():
    moment = datetime(2026, 7, 24, 22, 30, tzinfo=timezone.utc)

    assert _calibration_session("GPW", moment) == "2026-07-25"
    assert _calibration_session("USA", moment) == "2026-07-24"


def test_calibration_vector_clamps_legacy_iv_rank():
    iv_index = FEATURE_NAMES.index("iv_rank")

    assert _vector({"iv_rank": 141.4})[iv_index] == 100.0
    assert _vector({"iv_rank": -12.0})[iv_index] == 0.0


def test_finalized_record_restores_calibrated_probability_scale():
    row = SimpleNamespace(
        action="SELL", confidence=77.5,
        probability_buy=0.0, probability_sell=77.5, probability_no_trade=22.5,
        market="GPW", regime="range_bound", calibration_scope="market_regime",
        calibration_sample_size=6000, buy_threshold=47.5, sell_threshold=57.5,
        transaction_cost_pct=0.4, expected_gross_edge_pct=1.118,
        expected_net_edge_pct=0.718, uncertainty_pct=0.438,
        no_trade_reason=None,
    )

    decision = _decision_from_finalized_record(row)

    assert decision.action == "SELL"
    assert decision.confidence_probability == 0.775
    assert decision.probability_sell == 0.775
    assert decision.probability_no_trade == 0.225
    assert decision.sell_threshold == 0.575


def test_calibration_cache_stays_frozen_until_next_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'frozen-calibration.db'}")
    calls = []
    sentinel = object()
    monkeypatch.setattr(
        "app.services.recommendation_calibration._fit_segment",
        lambda *_args, **_kwargs: calls.append("fit") or sentinel,
    )
    friday_snapshot = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)
    monday_snapshot = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    invalidate_calibration_cache(force=True)
    with Session(engine) as db:
        assert _cached_fit(
            db, "GPW", "range_bound", "market_regime", at=friday_snapshot
        ) is sentinel
        assert _cached_fit(
            db, "GPW", "range_bound", "market_regime", at=friday_snapshot
        ) is sentinel
        invalidate_calibration_cache()
        assert _cached_fit(
            db, "GPW", "range_bound", "market_regime", at=friday_snapshot
        ) is sentinel
        assert calls == ["fit"]

        assert _cached_fit(
            db, "GPW", "range_bound", "market_regime", at=monday_snapshot
        ) is sentinel
        assert calls == ["fit", "fit"]
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
    assert "KUP" in (_forecast_consensus_veto(
        "KUP",
        bearish[0],
        SimpleNamespace(direction="up", up_probability=0.52),
        bearish[2],
    ) or "")
    assert _forecast_consensus_veto(
        "KUP",
        SimpleNamespace(direction="down", up_probability=0.49),
        SimpleNamespace(direction="up", up_probability=0.51),
        SimpleNamespace(direction="down", up_probability=0.49),
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
