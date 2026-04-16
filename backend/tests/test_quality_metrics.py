from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.repositories.assets import list_assets
from app.seed import seed_database
from app.services.feature_builder import rebuild_all_features_and_forecasts
from app.services.outcome_evaluator import evaluate_asset_outcomes
from app.services.quality_metrics import (
    build_forecast_quality_summary,
    build_thesis_quality_by_horizon,
    build_thesis_quality_summary,
)


def test_quality_metrics_services(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'quality.db'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_database(db)
        rebuild_all_features_and_forecasts(db, list_assets(db))
        evaluate_asset_outcomes(db, "nvda", limit=100)

        thesis_summary = build_thesis_quality_summary(db, "nvda", limit=100)
        assert thesis_summary.asset_id == "nvda"
        assert thesis_summary.total_outcomes >= 1

        by_horizon = build_thesis_quality_by_horizon(db, "nvda", limit=100)
        assert len(by_horizon) >= 1
        assert all(item.asset_id == "nvda" for item in by_horizon)

        forecast_summary = build_forecast_quality_summary(db, "nvda", limit=100)
        assert len(forecast_summary) >= 1
        assert all(item.asset_id == "nvda" for item in forecast_summary)
