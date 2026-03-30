"""Tests for curb and sidewalk generation."""

import pytest
from shapely.geometry import LineString
from app.services.geometry.models import RoadSegment
from app.services.geometry.road_edges import generate_road_edges
from app.services.geometry.curbs import generate_curbs, CURB_WIDTH_M
from app.services.geometry.sidewalks import generate_sidewalks


def _make_edges(width=6.0, highway_type="residential"):
    seg = RoadSegment(
        centerline=LineString([(500000, 4500000), (500000, 4500100)]),
        name="Test Rd",
        highway_type=highway_type,
        classification="local",
        width_m=width,
        lanes=2,
        lane_width_m=3.0,
    )
    left, right = generate_road_edges(seg)
    return seg, left, right


# --- Curb tests ---

def test_curb_lines_exist():
    """Curb lines exist outside road edges for residential."""
    seg, left, right = _make_edges(highway_type="residential")
    lc, rc = generate_curbs(left, right, "residential", "Test Rd")
    assert lc is not None
    assert rc is not None


def test_curb_distance_from_edge():
    """Distance from road edge to curb = 0.15m (+/- 0.05m)."""
    seg, left, right = _make_edges()
    lc, rc = generate_curbs(left, right, "residential", "Test Rd")
    left_mid = left.interpolate(0.5, normalized=True)
    curb_mid = lc.interpolate(0.5, normalized=True)
    dist = left_mid.distance(curb_mid)
    assert abs(dist - CURB_WIDTH_M) < 0.05


def test_no_curbs_for_motorway():
    """No curbs generated for motorway."""
    seg, left, right = _make_edges(highway_type="motorway")
    lc, rc = generate_curbs(left, right, "motorway", "Highway")
    assert lc is None
    assert rc is None


def test_no_curbs_for_track():
    """No curbs for track type."""
    seg, left, right = _make_edges(highway_type="track")
    lc, rc = generate_curbs(left, right, "track", "Path")
    assert lc is None
    assert rc is None


def test_curbs_for_primary():
    """Curbs generated for primary roads."""
    seg, left, right = _make_edges(highway_type="primary")
    lc, rc = generate_curbs(left, right, "primary", "Main St")
    assert lc is not None
    assert rc is not None


# --- Sidewalk tests ---

def test_sidewalk_both_sides():
    """Residential road with sidewalk=both has sidewalks on both sides."""
    seg, left, right = _make_edges()
    lc, rc = generate_curbs(left, right, "residential", "Test Rd")
    ls, rs = generate_sidewalks(lc, rc, "residential", "local", "both", "Test Rd")
    assert ls is not None
    assert rs is not None


def test_sidewalk_left_only():
    """Road with sidewalk=left has sidewalk on left side only."""
    seg, left, right = _make_edges()
    lc, rc = generate_curbs(left, right, "residential", "Test Rd")
    ls, rs = generate_sidewalks(lc, rc, "residential", "local", "left", "Test Rd")
    assert ls is not None
    assert rs is None


def test_sidewalk_no():
    """Road with sidewalk=no has no sidewalks."""
    seg, left, right = _make_edges()
    lc, rc = generate_curbs(left, right, "residential", "Test Rd")
    ls, rs = generate_sidewalks(lc, rc, "residential", "local", "no", "Test Rd")
    assert ls is None
    assert rs is None


def test_motorway_no_sidewalks():
    """Motorway has no sidewalks regardless of tag."""
    seg, left, right = _make_edges(highway_type="motorway")
    # No curbs for motorway, but pass fake edges
    ls, rs = generate_sidewalks(left, right, "motorway", "main", "both", "Hwy")
    assert ls is None
    assert rs is None


def test_sidewalk_distance_from_edge():
    """Sidewalk outer edge distance from road edge = curb_width + sidewalk_width."""
    seg, left, right = _make_edges(width=6.0)
    lc, rc = generate_curbs(left, right, "residential", "Test Rd")
    ls, rs = generate_sidewalks(lc, rc, "residential", "local", "both", "Test Rd")

    # Expected: 0.15m (curb) + 1.5m (local sidewalk) = 1.65m from road edge
    edge_mid = left.interpolate(0.5, normalized=True)
    sw_mid = ls.interpolate(0.5, normalized=True)
    dist = edge_mid.distance(sw_mid)
    expected = CURB_WIDTH_M + 1.5
    assert abs(dist - expected) < 0.2
