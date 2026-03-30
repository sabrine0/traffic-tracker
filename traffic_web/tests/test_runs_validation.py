from traffic_web.app.auth.passwords import hash_password
from traffic_web.app.auth.sessions import SESSION_COOKIE_NAME, create_session
from traffic_web.app.db.models import User


def test_runs_create_invalid_camera_id_returns_400(client, db_session):
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

    response = client.post(
        "/admin/runs/new",
        data={
            "job_id": "job1",
            "status": "uploaded",
            "camera_id": "999",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Camera" in response.text
