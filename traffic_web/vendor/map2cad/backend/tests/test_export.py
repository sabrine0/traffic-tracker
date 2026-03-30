import json
import os
from unittest.mock import patch, MagicMock
from tests.conftest import VALID_POLYGON, LARGE_POLYGON

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_overpass_response.json")


def _mock_overpass():
    with open(FIXTURE_PATH) as f:
        fixture = json.load(f)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fixture
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_export_valid_polygon(client):
    with patch("app.services.overpass_client.requests.post", return_value=_mock_overpass()):
        resp = client.post("/api/export", json={"polygon": VALID_POLYGON})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "download_url" in data
    assert "stats" in data


def test_export_with_options(client):
    with patch("app.services.overpass_client.requests.post", return_value=_mock_overpass()):
        resp = client.post("/api/export", json={
            "polygon": VALID_POLYGON,
            "options": {"lane_markings": False, "sidewalks": True},
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"


def test_export_missing_polygon(client):
    resp = client.post("/api/export", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_REQUEST"


def test_export_non_json(client):
    resp = client.post("/api/export", data="not json", content_type="text/plain")
    assert resp.status_code == 400


def test_export_too_few_vertices(client):
    resp = client.post("/api/export", json={"polygon": [[0, 0], [1, 1]]})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_POLYGON"
    assert "at least 3" in data["message"]


def test_export_invalid_coords(client):
    resp = client.post("/api/export", json={"polygon": [[200, 0], [0, 0], [0, 1]]})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "longitude out of range" in data["message"]


def test_export_area_too_large(client):
    resp = client.post("/api/export", json={"polygon": LARGE_POLYGON})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "AREA_TOO_LARGE"
