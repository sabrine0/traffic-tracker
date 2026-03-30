def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] in ("healthy", "degraded")
    assert "components" in data
    assert data["components"]["app"] == "ok"


def test_404_returns_json(client):
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["code"] == "NOT_FOUND"
