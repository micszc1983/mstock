from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.repositories.assets import list_assets
from app.repositories.theses import get_latest_thesis, list_thesis_history
from app.seed import seed_database
from app.services.feature_builder import rebuild_all_features_and_forecasts


def test_rebuild_persists_thesis_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'theses.db'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_database(db)
        rebuilt = rebuild_all_features_and_forecasts(db, list_assets(db))
        assert rebuilt >= 1

        latest = get_latest_thesis(db, "nvda")
        assert latest is not None
        assert latest.asset_id == "nvda"
        assert latest.thesis
        assert latest.anti_thesis

        history = list_thesis_history(db, "nvda", limit=10)
        assert len(history) >= 1
