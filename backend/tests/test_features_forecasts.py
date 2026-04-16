from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.repositories.assets import list_assets
from app.repositories.features import get_latest_feature_snapshot, list_feature_history
from app.repositories.forecasts import get_latest_forecasts
from app.seed import seed_database
from app.services.feature_builder import rebuild_all_features_and_forecasts


def test_rebuild_features_and_forecasts_persists_snapshots(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'features.db'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_database(db)
        rebuilt = rebuild_all_features_and_forecasts(db, list_assets(db))
        assert rebuilt >= 1

        snapshot = get_latest_feature_snapshot(db, "nvda")
        assert snapshot is not None
        assert snapshot.asset_id == "nvda"
        assert snapshot.last_price > 0
        assert 0 <= snapshot.fragility_score <= 100

        forecasts = get_latest_forecasts(db, "nvda")
        assert len(forecasts) == 3
        assert {row.horizon for row in forecasts} == {"1d", "5d", "20d"}
