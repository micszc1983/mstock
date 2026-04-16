from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db


@pytest.fixture()
def test_app(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_SYNC_ENABLED", "false")
    db_file = tmp_path / "test.db"

    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    from app.seed import seed_database
    with TestingSessionLocal() as db:
        seed_database(db)

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
