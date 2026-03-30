"""Tests for lane marking generation."""

import pytest
from shapely.geometry import LineString
from app.services.geometry.models import RoadSegment
from app.services.geometry.lane_markings import generate_lane_markings


def _make_segment(lanes=2, width=None, oneway=False, lane_width=3.0):
    if width is None:
        width = lanes * lane_width
    return RoadSegment(
        centerline=LineString([(500000, 4500000), (500000, 4500100)]),
        name="Test Rd",
        highway_type="residential",
        classification="local",
        width_m=width,
        lanes=lanes,
        lane_width_m=lane_width,
        oneway=oneway,
        sidewalk="both",
        has_median=False,
    )


def test_two_lane_one_divider():
    """2-lane road has 1 divider."""
    seg = _make_segment(lanes=2)
    markings = generate_lane_markings(seg)
    assert len(markings) == 1


def test_four_lane_three_dividers():
    """4-lane road has 3 dividers."""
    seg = _make_segment(lanes=4)
    markings = generate_lane_markings(seg)
    assert len(markings) == 3


def test_two_way_center_solid():
    """Two-way road: center divider is solid."""
    seg = _make_segment(lanes=2, oneway=False)
    markings = generate_lane_markings(seg)
    assert len(markings) == 1
    assert markings[0][1] == "solid"


def test_four_lane_two_way_center_solid():
    """4-lane two-way: center divider is solid, others dashed."""
    seg = _make_segment(lanes=4, oneway=False)
    markings = generate_lane_markings(seg)
    linetypes = [m[1] for m in markings]
    assert "solid" in linetypes
    # Center is index 2 (lane boundary at lanes//2 = 2)
    assert markings[1][1] == "solid"  # i=2 → center_idx=2
    assert markings[0][1] == "dashed"
    assert markings[2][1] == "dashed"


def test_oneway_all_dashed():
    """One-way road: all dividers are dashed."""
    seg = _make_segment(lanes=3, oneway=True)
    markings = generate_lane_markings(seg)
    assert len(markings) == 2
    for line, linetype in markings:
        assert linetype == "dashed"


def test_single_lane_no_markings():
    """Single lane road has no markings."""
    seg = _make_segment(lanes=1)
    markings = generate_lane_markings(seg)
    assert len(markings) == 0


def test_divider_offset_from_centerline():
    """Divider position: offset from centerline matches expected lane boundary."""
    seg = _make_segment(lanes=2, width=6.0, lane_width=3.0)
    markings = generate_lane_markings(seg)
    assert len(markings) == 1
    divider = markings[0][0]
    # For 2-lane, 6m wide road: divider at offset 0 (center)
    # Distance from centerline midpoint to divider midpoint should be ~0
    cl_mid = seg.centerline.interpolate(0.5, normalized=True)
    div_mid = divider.interpolate(0.5, normalized=True)
    assert cl_mid.distance(div_mid) < 0.5
