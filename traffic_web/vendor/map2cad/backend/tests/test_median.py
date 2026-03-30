"""Tests for median geometry generation on divided roads."""

import pytest
from shapely.geometry import LineString
from app.services.geometry.models import RoadSegment
from app.services.geometry.road_edges import generate_divided_road_edges


def _make_divided_segment(lanes=6, width=10.5, median_width=2.0):
    return RoadSegment(
        centerline=LineString([(500000, 4500000), (500000, 4500100)]),
        name="Highway",
        highway_type="motorway",
        classification="main",
        width_m=width,
        lanes=lanes,
        lane_width_m=3.5,
        oneway=False,
        sidewalk="no",
        has_median=True,
        median_width_m=median_width,
    )


def test_motorway_two_carriageways():
    """Motorway with 6 lanes produces two carriageways of 3 lanes each."""
    seg = _make_divided_segment(lanes=6)
    result = generate_divided_road_edges(seg)
    assert result["left_carriageway_lanes"] == 3
    assert result["right_carriageway_lanes"] == 3


def test_carriageway_separation_equals_median():
    """Carriageway centerlines separated by median width."""
    seg = _make_divided_segment(median_width=2.0)
    result = generate_divided_road_edges(seg)
    left_cl = result["left_centerline"]
    right_cl = result["right_centerline"]
    assert left_cl is not None
    assert right_cl is not None
    left_mid = left_cl.interpolate(0.5, normalized=True)
    right_mid = right_cl.interpolate(0.5, normalized=True)
    separation = left_mid.distance(right_mid)
    assert abs(separation - 2.0) < 0.5


def test_each_carriageway_has_edges():
    """Each carriageway has its own left and right edges."""
    seg = _make_divided_segment()
    result = generate_divided_road_edges(seg)
    left_edges = result["left_carriageway_edges"]
    right_edges = result["right_carriageway_edges"]
    # At least one edge per carriageway should exist
    assert left_edges[0] is not None or left_edges[1] is not None
    assert right_edges[0] is not None or right_edges[1] is not None


def test_median_inner_edges_exist():
    """Median inner edges exist between carriageways."""
    seg = _make_divided_segment()
    result = generate_divided_road_edges(seg)
    median = result["median_lines"]
    assert median[0] is not None or median[1] is not None


def test_total_width():
    """Total width = left_carriageway + median + right_carriageway."""
    seg = _make_divided_segment(width=10.5, median_width=2.0, lanes=6)
    result = generate_divided_road_edges(seg)
    expected_cw = (10.5 - 2.0) / 2.0  # 4.25 each
    assert abs(result["left_carriageway_width"] - expected_cw) < 0.01
    assert abs(result["right_carriageway_width"] - expected_cw) < 0.01
