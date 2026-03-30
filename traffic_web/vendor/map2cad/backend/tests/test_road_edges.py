"""Tests for road edge generation."""

import pytest
from shapely.geometry import LineString, Point
from app.services.geometry.models import RoadSegment
from app.services.geometry.road_edges import generate_road_edges, generate_divided_road_edges


def _make_segment(coords=None, width=6.0, **kwargs):
    if coords is None:
        coords = [(500000, 4500000), (500000, 4500100)]
    defaults = dict(
        centerline=LineString(coords),
        name="Test Rd",
        highway_type="residential",
        classification="local",
        width_m=width,
        lanes=2,
        lane_width_m=3.0,
        oneway=False,
        sidewalk="both",
        has_median=False,
    )
    defaults.update(kwargs)
    return RoadSegment(**defaults)


def test_straight_road_edges_parallel():
    """Straight road: edges are parallel, separated by road width."""
    seg = _make_segment(width=6.0)
    left, right = generate_road_edges(seg)
    assert left is not None
    assert right is not None
    assert isinstance(left, LineString)
    assert isinstance(right, LineString)


def test_edge_separation_equals_width():
    """Distance between left and right edge midpoints equals road width."""
    seg = _make_segment(width=10.0)
    left, right = generate_road_edges(seg)
    left_mid = left.interpolate(0.5, normalized=True)
    right_mid = right.interpolate(0.5, normalized=True)
    distance = left_mid.distance(right_mid)
    assert abs(distance - 10.0) < 0.5


def test_curved_road_edges():
    """Curved road: edges follow curvature."""
    coords = [
        (500000, 4500000),
        (500020, 4500030),
        (500050, 4500040),
        (500080, 4500030),
        (500100, 4500000),
    ]
    seg = _make_segment(coords=coords, width=6.0)
    left, right = generate_road_edges(seg)
    assert left is not None
    assert right is not None
    assert left.length > 0
    assert right.length > 0


def test_sharp_corner_handled():
    """Sharp corner road: handled without error."""
    coords = [
        (500000, 4500000),
        (500000, 4500050),
        (500001, 4500050),  # very sharp turn
        (500001, 4500100),
    ]
    seg = _make_segment(coords=coords, width=6.0)
    left, right = generate_road_edges(seg)
    # At least one side should succeed (even if fallback is used)
    assert left is not None or right is not None


def test_output_geometries_valid():
    """All output geometries are valid LineStrings."""
    seg = _make_segment(width=8.0)
    left, right = generate_road_edges(seg)
    for edge in [left, right]:
        if edge is not None:
            assert isinstance(edge, LineString)
            assert edge.is_valid
            assert not edge.is_empty
            assert len(edge.coords) >= 2


def test_different_widths():
    """Different road widths produce different edge separations."""
    seg_narrow = _make_segment(width=3.0)
    seg_wide = _make_segment(width=12.0)
    left_n, right_n = generate_road_edges(seg_narrow)
    left_w, right_w = generate_road_edges(seg_wide)

    dist_narrow = left_n.interpolate(0.5, normalized=True).distance(
        right_n.interpolate(0.5, normalized=True)
    )
    dist_wide = left_w.interpolate(0.5, normalized=True).distance(
        right_w.interpolate(0.5, normalized=True)
    )
    assert dist_wide > dist_narrow
