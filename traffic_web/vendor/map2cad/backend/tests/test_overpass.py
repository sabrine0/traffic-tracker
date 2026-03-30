import json
import os
from unittest.mock import patch, MagicMock
from app.services.overpass_client import build_overpass_query, query_overpass


POLYGON = [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]]
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_overpass_response.json")


def test_build_query_format():
    query = build_overpass_query(POLYGON, timeout=30)
    assert '[out:json][timeout:30]' in query
    assert 'way["highway"]' in query
    assert '(poly:"' in query
    # Verify lat lon order (not lng lat)
    assert "40.75 -73.99" in query


def test_build_query_polygon_coords():
    query = build_overpass_query([[-1.5, 51.5], [-1.4, 51.5], [-1.4, 51.6]], timeout=60)
    assert "51.5 -1.5" in query
    assert "51.5 -1.4" in query
    assert "51.6 -1.4" in query


def test_build_query_with_feature_layers():
    """Union query includes fragments for enabled layers."""
    layers = {"buildings": True, "railways": True, "parking": False}
    query = build_overpass_query(POLYGON, timeout=60, enabled_layers=layers)
    assert 'way["building"]' in query
    assert 'way["railway"' in query
    assert 'way["amenity"="parking"]' not in query
    assert 'way["highway"]' in query  # always included


def test_build_query_with_all_layers():
    layers = {
        "buildings": True, "landuse": True, "railways": True,
        "parking": True, "traffic_signals": True, "street_furniture": True,
        "cycling": True, "utilities": True,
    }
    query = build_overpass_query(POLYGON, enabled_layers=layers)
    assert 'way["building"]' in query
    assert 'way["leisure"="park"]' in query
    assert 'way["natural"="water"]' in query
    assert 'way["railway"' in query
    assert 'way["amenity"="parking"]' in query
    assert 'node["highway"="traffic_signals"]' in query
    assert 'node["natural"="tree"]' in query
    assert 'way["highway"="cycleway"]' in query
    assert 'node["man_made"="manhole"]' in query
    assert 'way["power"' in query


def test_build_query_no_layers_highway_only():
    """No enabled_layers still includes highway query."""
    query = build_overpass_query(POLYGON)
    assert 'way["highway"]' in query
    assert 'way["building"]' not in query


def test_query_overpass_parses_response():
    with open(FIXTURE_PATH) as f:
        fixture = json.load(f)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fixture
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.overpass_client.requests.post", return_value=mock_resp):
        result = query_overpass(POLYGON)

    assert "ways" in result
    assert "nodes" in result
    assert len(result["ways"]) == 3
    assert result["ways"][0]["id"] == 100
    assert result["ways"][0]["tags"]["name"] == "Test Street"
    assert len(result["ways"][0]["nodes"]) == 3
    assert result["ways"][0]["nodes"][0]["lat"] == 40.75


def test_query_overpass_empty_response():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"elements": []}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.overpass_client.requests.post", return_value=mock_resp):
        result = query_overpass(POLYGON)

    assert result == {"ways": [], "nodes": []}


def test_query_overpass_returns_tagged_nodes():
    """Nodes with tags (e.g. traffic signals) are returned in the nodes list."""
    fixture = {
        "elements": [
            {"type": "node", "id": 1, "lat": 40.75, "lon": -73.99,
             "tags": {"highway": "traffic_signals"}},
            {"type": "node", "id": 2, "lat": 40.76, "lon": -73.98},  # no tags
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fixture
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.overpass_client.requests.post", return_value=mock_resp):
        result = query_overpass(POLYGON)

    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["id"] == 1
    assert result["nodes"][0]["tags"]["highway"] == "traffic_signals"
