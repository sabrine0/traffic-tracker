from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from traffic_web.app.auth.bootstrap import ensure_admin_user
from traffic_web.app.auth.passwords import hash_password
from traffic_web.app.db.models import Base, User


def test_bootstrap_collision_no_crash(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user_email = User(
        email="a@example.com",
        username="alice",
        password_hash=hash_password("pw1"),
        role="viewer",
        is_active=True,
    )
    user_username = User(
        email="b@example.com",
        username="admin",
        password_hash=hash_password("pw2"),
        role="viewer",
        is_active=True,
    )
    db.add_all([user_email, user_username])
    db.commit()

    monkeypatch.setenv("TRAFFIC_TRACKER_ADMIN_EMAIL", "a@example.com")
    monkeypatch.setenv("TRAFFIC_TRACKER_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("TRAFFIC_TRACKER_ADMIN_PASSWORD", "secret")

    ensure_admin_user(db)

    db.expire_all()
    refreshed_email = db.query(User).filter(User.email == "a@example.com").first()
    refreshed_username = db.query(User).filter(User.email == "b@example.com").first()
    assert refreshed_email.username == "alice"
    assert refreshed_username.username == "admin"
    db.close()
