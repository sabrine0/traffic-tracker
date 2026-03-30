from urllib.parse import parse_qs, urlparse


def test_admin_redirects_to_login(client):
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    location = response.headers.get("location")
    assert location is not None
    parsed = urlparse(location)
    assert parsed.path == "/admin/login"
    params = parse_qs(parsed.query)
    assert params.get("next", [None])[0] == "/admin"
