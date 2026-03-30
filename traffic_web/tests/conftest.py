import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from traffic_web.app.main import app
from traffic_web.app.db.models import Base
from traffic_web.app.auth.deps import get_db


@pytest.fixture(autouse=True)
def _disable_startup(monkeypatch):
    monkeypatch.setenv("TRAFFIC_TRACKER_AUTO_CREATE", "0")
    monkeypatch.delenv("TRAFFIC_TRACKER_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("TRAFFIC_TRACKER_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("TRAFFIC_TRACKER_ADMIN_USERNAME", raising=False)


@pytest.fixture()
def db_sessionmaker():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


@pytest.fixture()
def client(db_sessionmaker):
    def override_get_db():
        db = db_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(db_sessionmaker):
    db = db_sessionmaker()
    try:
        yield db
    finally:
        db.close()
