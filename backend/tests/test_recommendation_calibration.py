from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import AssetORM, PortfolioPositionORM
from app.db.session import Base
from app.services.recommendation_calibration import (
    _tune_threshold,
    market_segment,
)
from app.services.recommendation_engine import build_recommendation


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
