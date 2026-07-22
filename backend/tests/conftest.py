from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db


@pytest.fixture(autouse=True)
def _enable_test_mode(monkeypatch):
    """Keep provider calls and seed data deterministic in every test."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "testing", True)


@pytest.fixture()
def test_app(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_SYNC_ENABLED", "false")
    from app.core.config import settings
    db_file = tmp_path / "test.db"

    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    from app.db import models as _models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    from app.seed import seed_database
    with TestingSessionLocal() as db:
        seed_database(db)
        from app.repositories.assets import list_assets
        from app.services.feature_builder import rebuild_all_features_and_forecasts

        rebuild_all_features_and_forecasts(db, list_assets(db))

    from main import app
    from app.services.scheduler import stop_scheduler

    stop_scheduler()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
