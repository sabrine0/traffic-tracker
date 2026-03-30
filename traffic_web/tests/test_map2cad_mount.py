from urllib.parse import parse_qs, urlparse

from traffic_web.app.auth.sessions import SESSION_COOKIE_NAME, create_session
from traffic_web.app.db.models import User
from traffic_web.app.auth.passwords import hash_password


def test_map2cad_redirects_to_login(client):
    response = client.get("/map2cad", follow_redirects=False)
    assert response.status_code == 303
    parsed = urlparse(response.headers["location"])
    assert parsed.path == "/admin/login"
    assert parse_qs(parsed.query)["next"] == ["/map2cad"]


def test_map2cad_export_mount_handles_validation(client, db_session):
    admin = User(
        email="admin@example.com",
        username="admin",
        full_name="Admin",
        password_hash=hash_password("pw"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    token = create_session(db_session, admin, ip="test", user_agent="pytest")
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post("/map2cad-api/api/export", json={})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
