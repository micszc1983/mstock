from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.repositories.assets import list_assets
from app.repositories.outcomes import list_outcomes_for_asset
from app.repositories.theses import get_latest_thesis
from app.seed import seed_database
from app.services.feature_builder import rebuild_all_features_and_forecasts
from app.services.outcome_evaluator import evaluate_asset_outcomes, evaluate_thesis_outcomes


def test_evaluate_asset_outcomes_persists_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'outcomes.db'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_database(db)
        rebuild_all_features_and_forecasts(db, list_assets(db))

        created = evaluate_asset_outcomes(db, "nvda", limit=20)
        assert created >= 1

        outcomes = list_outcomes_for_asset(db, "nvda", limit=100)
        assert len(outcomes) >= 1
        assert outcomes[0].asset_id == "nvda"
        assert outcomes[0].horizon in {"1d", "5d", "20d"}


def test_evaluate_single_thesis(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'single_outcomes.db'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_database(db)
        rebuild_all_features_and_forecasts(db, list_assets(db))
        thesis = get_latest_thesis(db, "nvda")
        assert thesis is not None

        created = evaluate_thesis_outcomes(db, thesis)
        assert created >= 1
