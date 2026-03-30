"""Unit tests for feature_parser module."""

import pytest
from shapely.geometry import Polygon, Point

from app.services.feature_parser import (
    parse_buildings,
    parse_landuse,
    parse_railways,
    parse_parking,
    parse_point_features,
    parse_cycleways,
    parse_utilities,
)
from app.services.geometry.projection import ProjectionHelper


@pytest.fixture
def proj():
    """ProjectionHelper centered on NYC."""
    return ProjectionHelper(-73.99, 40.75)


@pytest.fixture
def boundary(proj):
    """Large boundary polygon covering the test area."""
    return proj.transform_polygon([
        [-74.0, 40.74], [-73.98, 40.74], [-73.98, 40.76], [-74.0, 40.76]
    ])


def _closed_way(way_id, tags, nodes=None):
    """Helper to create a closed way dict."""
    if nodes is None:
        nodes = [
            {"lat": 40.750, "lon": -73.990},
            {"lat": 40.750, "lon": -73.989},
            {"lat": 40.751, "lon": -73.989},
            {"lat": 40.751, "lon": -73.990},
            {"lat": 40.750, "lon": -73.990},  # closed
        ]
    return {"id": way_id, "nodes": nodes, "tags": tags}


def _line_way(way_id, tags, nodes=None):
    """Helper to create a line way dict."""
    if nodes is None:
        nodes = [
            {"lat": 40.750, "lon": -73.990},
            {"lat": 40.752, "lon": -73.990},
        ]
    return {"id": way_id, "nodes": nodes, "tags": tags}


def _node(node_id, lat, lon, tags):
    """Helper to create a node dict."""
    return {"id": node_id, "lat": lat, "lon": lon, "tags": tags}


# --- Buildings ---

class TestParseBuildings:
    def test_parses_building(self, proj, boundary):
        ways = [_closed_way(1, {"building": "yes", "name": "Test Bldg"})]
        result = parse_buildings(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].building_type == "yes"
        assert result[0].name == "Test Bldg"
        assert isinstance(result[0].polygon, Polygon)

    def test_skips_non_building(self, proj, boundary):
        ways = [_closed_way(1, {"highway": "residential"})]
        result = parse_buildings(ways, proj, boundary)
        assert len(result) == 0

    def test_skips_degenerate_polygon(self, proj, boundary):
        nodes = [{"lat": 40.75, "lon": -73.99}, {"lat": 40.75, "lon": -73.99}]
        ways = [_closed_way(1, {"building": "yes"}, nodes)]
        result = parse_buildings(ways, proj, boundary)
        assert len(result) == 0


# --- Land Use ---

class TestParseLanduse:
    def test_parses_park(self, proj, boundary):
        ways = [_closed_way(1, {"leisure": "park", "name": "Central Park"})]
        result = parse_landuse(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].landuse_type == "park"

    def test_parses_water(self, proj, boundary):
        ways = [_closed_way(1, {"natural": "water"})]
        result = parse_landuse(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].landuse_type == "water"

    def test_parses_industrial(self, proj, boundary):
        ways = [_closed_way(1, {"landuse": "industrial"})]
        result = parse_landuse(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].landuse_type == "industrial"

    def test_skips_unknown_landuse(self, proj, boundary):
        ways = [_closed_way(1, {"landuse": "farmland"})]
        result = parse_landuse(ways, proj, boundary)
        assert len(result) == 0


# --- Railways ---

class TestParseRailways:
    def test_parses_rail(self, proj, boundary):
        ways = [_line_way(1, {"railway": "rail", "name": "Metro Line"})]
        result = parse_railways(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].railway_type == "rail"

    def test_parses_tram(self, proj, boundary):
        ways = [_line_way(1, {"railway": "tram"})]
        result = parse_railways(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].railway_type == "tram"

    def test_skips_invalid_railway_type(self, proj, boundary):
        ways = [_line_way(1, {"railway": "station"})]
        result = parse_railways(ways, proj, boundary)
        assert len(result) == 0


# --- Parking ---

class TestParseParking:
    def test_parses_parking_lot(self, proj, boundary):
        ways = [_closed_way(1, {"amenity": "parking"})]
        result = parse_parking(ways, [], proj, boundary)
        assert len(result) == 1
        assert result[0].polygon is not None

    def test_parses_parking_space_node(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"amenity": "parking_space"})]
        result = parse_parking([], nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].point is not None
        assert result[0].parking_type == "street"


# --- Point Features ---

class TestParsePointFeatures:
    def test_parses_traffic_signal(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"highway": "traffic_signals"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].feature_type == "traffic_signal"

    def test_parses_tree(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"natural": "tree"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].feature_type == "tree"

    def test_parses_bench(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"amenity": "bench"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].feature_type == "bench"

    def test_parses_street_lamp(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"highway": "street_lamp"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].feature_type == "street_lamp"

    def test_parses_manhole(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"man_made": "manhole"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].feature_type == "manhole"

    def test_skips_unknown_tag(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"shop": "supermarket"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 0

    def test_outside_boundary_skipped(self, proj, boundary):
        nodes = [_node(1, 50.0, -73.990, {"natural": "tree"})]
        result = parse_point_features(nodes, proj, boundary)
        assert len(result) == 0


# --- Cycleways ---

class TestParseCycleways:
    def test_parses_cycleway(self, proj, boundary):
        ways = [_line_way(1, {"highway": "cycleway", "name": "Bike Path"})]
        result = parse_cycleways(ways, proj, boundary)
        assert len(result) == 1
        assert result[0].cycleway_type == "path"

    def test_skips_road_with_cycleway_tag(self, proj, boundary):
        """Roads with cycleway=lane should not be parsed as separate cycleways."""
        ways = [_line_way(1, {"highway": "residential", "cycleway": "lane"})]
        result = parse_cycleways(ways, proj, boundary)
        assert len(result) == 0


# --- Utilities ---

class TestParseUtilities:
    def test_parses_power_line(self, proj, boundary):
        ways = [_line_way(1, {"power": "line"})]
        result = parse_utilities(ways, [], proj, boundary)
        assert len(result) == 1
        assert result[0].utility_type == "power_line"

    def test_parses_manhole_node(self, proj, boundary):
        nodes = [_node(1, 40.751, -73.990, {"man_made": "manhole"})]
        result = parse_utilities([], nodes, proj, boundary)
        assert len(result) == 1
        assert result[0].utility_type == "manhole"

    def test_parses_minor_power_line(self, proj, boundary):
        ways = [_line_way(1, {"power": "minor_line"})]
        result = parse_utilities(ways, [], proj, boundary)
        assert len(result) == 1
        assert result[0].utility_type == "minor_power_line"
