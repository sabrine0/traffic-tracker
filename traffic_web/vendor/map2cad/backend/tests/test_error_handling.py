"""Comprehensive error handling tests for all error scenarios."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
import requests

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


# --- Validation error tests ---

def test_nan_coordinates(client):
    resp = client.post("/api/export", json={"polygon": [[float("nan"), 40.0], [0, 0], [1, 1]]})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_POLYGON"


def test_infinity_coordinates(client):
    resp = client.post("/api/export", json={"polygon": [[float("inf"), 40.0], [0, 0], [1, 1]]})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_POLYGON"


def test_self_intersecting_polygon(client):
    # Bowtie polygon (self-intersecting)
    polygon = [[0, 0], [1, 1], [1, 0], [0, 1]]
    resp = client.post("/api/export", json={"polygon": polygon})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_POLYGON"


def test_too_many_vertices(client):
    polygon = [[i * 0.0001, i * 0.0001] for i in range(1001)]
    resp = client.post("/api/export", json={"polygon": polygon})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_POLYGON"
    assert "1000" in data["message"]


def test_area_too_large(client):
    resp = client.post("/api/export", json={"polygon": LARGE_POLYGON})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "AREA_TOO_LARGE"


def test_non_json_body(client):
    resp = client.post("/api/export", data="not json", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_REQUEST"


def test_missing_polygon_field(client):
    resp = client.post("/api/export", json={})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_REQUEST"


def test_invalid_coord_type(client):
    resp = client.post("/api/export", json={"polygon": [["a", "b"], [0, 0], [1, 1]]})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_POLYGON"


def test_two_vertices_rejected(client):
    resp = client.post("/api/export", json={"polygon": [[0, 0], [1, 1]]})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "INVALID_POLYGON"
    assert "at least 3" in data["message"]


def test_longitude_out_of_range(client):
    resp = client.post("/api/export", json={"polygon": [[200, 0], [0, 0], [0, 1]]})
    assert resp.status_code == 400
    assert "longitude out of range" in resp.get_json()["message"]


def test_latitude_out_of_range(client):
    resp = client.post("/api/export", json={"polygon": [[0, 100], [0, 0], [1, 1]]})
    assert resp.status_code == 400
    assert "latitude out of range" in resp.get_json()["message"]


# --- Overpass error tests ---

def test_overpass_timeout(client):
    mock_resp = MagicMock()
    mock_resp.side_effect = requests.Timeout()
    with patch("app.services.overpass_client.requests.post", side_effect=requests.Timeout()):
        resp = client.post("/api/export", json={"polygon": VALID_POLYGON})
    assert resp.status_code == 504
    assert resp.get_json()["code"] == "OVERPASS_TIMEOUT"


def test_overpass_rate_limited(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status = MagicMock()
    with patch("app.services.overpass_client.requests.post", return_value=mock_resp):
        with patch("app.services.overpass_client.time.sleep"):  # skip wait
            resp = client.post("/api/export", json={"polygon": VALID_POLYGON})
    assert resp.status_code == 429
    assert resp.get_json()["code"] == "OVERPASS_RATE_LIMITED"


def test_overpass_server_error(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.raise_for_status = MagicMock(side_effect=requests.HTTPError())
    with patch("app.services.overpass_client.requests.post", return_value=mock_resp):
        resp = client.post("/api/export", json={"polygon": VALID_POLYGON})
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "OVERPASS_UNAVAILABLE"


def test_overpass_empty_result(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"elements": []}
    mock_resp.raise_for_status = MagicMock()
    with patch("app.services.overpass_client.requests.post", return_value=mock_resp):
        resp = client.post("/api/export", json={"polygon": VALID_POLYGON})
    assert resp.status_code == 500
    assert resp.get_json()["code"] == "NO_ROADS_FOUND"


# --- Download error tests ---

def test_download_nonexistent(client):
    resp = client.get("/downloads/nonexistent.dxf")
    assert resp.status_code == 404


def test_download_path_traversal(client):
    resp = client.get("/downloads/../../../etc/passwd")
    assert resp.status_code == 404


# --- Health check tests ---

def test_health_returns_components(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "components" in data
    assert data["components"]["app"] == "ok"


def test_health_degraded_when_overpass_unreachable(client):
    with patch("app.routes.health.requests.get", side_effect=Exception("timeout")):
        resp = client.get("/api/health")
    data = resp.get_json()
    assert data["status"] == "degraded"
    assert data["components"]["overpass"] == "unreachable"


# --- 404 handler ---

def test_404_returns_json(client):
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["code"] == "NOT_FOUND"


# --- Export with valid data (integration) ---

def test_export_success_with_mock(client):
    with patch("app.services.overpass_client.requests.post", return_value=_mock_overpass()):
        resp = client.post("/api/export", json={"polygon": VALID_POLYGON})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "warnings" in data
    assert isinstance(data["warnings"], list)


def test_export_with_options(client):
    with patch("app.services.overpass_client.requests.post", return_value=_mock_overpass()):
        resp = client.post("/api/export", json={
            "polygon": VALID_POLYGON,
            "options": {"lane_markings": False, "sidewalks": False},
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
