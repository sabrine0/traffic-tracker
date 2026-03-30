"""Tests for road geometry orchestrator."""

import pytest
from shapely.geometry import LineString
from app.services.geometry.models import RoadSegment
from app.services.geometry.road_builder import build_road_geometry


def _make_segment(name="Test Rd", highway_type="residential", width=6.0, lanes=2,
                  oneway=False, sidewalk="both", has_median=False, y_offset=0):
    return RoadSegment(
        centerline=LineString([
            (500000, 4500000 + y_offset),
            (500000, 4500100 + y_offset),
        ]),
        name=name,
        highway_type=highway_type,
        classification="local",
        width_m=width,
        lanes=lanes,
        lane_width_m=3.0,
        oneway=oneway,
        sidewalk=sidewalk,
        has_median=has_median,
    )


def test_five_roads_all_layers():
    """5 roads produce all expected layers."""
    segments = [
        _make_segment(name=f"Road {i}", y_offset=i * 200)
        for i in range(5)
    ]
    layers, warnings = build_road_geometry(segments)
    assert "ROAD_EDGES" in layers
    assert "CENTERLINES" in layers
    assert "LANE_MARKINGS" in layers
    assert len(warnings) == 0


def test_sidewalks_disabled():
    """Export with sidewalks=false produces no SIDEWALKS layer."""
    segments = [_make_segment()]
    layers, warnings = build_road_geometry(segments, {"sidewalks": False})
    assert "SIDEWALKS" not in layers


def test_lane_markings_disabled():
    """Export with lane_markings=false produces no LANE_MARKINGS layer."""
    segments = [_make_segment()]
    layers, warnings = build_road_geometry(segments, {"lane_markings": False})
    assert "LANE_MARKINGS" not in layers


def test_bad_geometry_skipped():
    """One bad road geometry is skipped, others processed."""
    good = _make_segment(name="Good Rd")
    # Create a degenerate segment that will cause an error
    bad = RoadSegment(
        centerline=LineString(),  # empty geometry
        name="Bad Rd",
        highway_type="residential",
    )
    layers, warnings = build_road_geometry([good, bad])
    assert len(warnings) == 1
    assert "Bad Rd" in warnings[0]
    assert "CENTERLINES" in layers
    assert len(layers["CENTERLINES"]) >= 1


def test_entity_counts_reasonable():
    """Entity counts per layer are reasonable for a simple road."""
    segments = [_make_segment(lanes=2, sidewalk="both")]
    layers, _ = build_road_geometry(segments)
    # 1 centerline
    assert len(layers["CENTERLINES"]) == 1
    # 2 road edges (left + right)
    assert len(layers["ROAD_EDGES"]) == 2
    # 1 lane marking (2-lane road has 1 divider)
    assert len(layers["LANE_MARKINGS"]) == 1


def test_divided_road_has_medians():
    """Divided road produces MEDIANS layer."""
    seg = _make_segment(
        name="Highway",
        highway_type="motorway",
        width=10.5,
        lanes=6,
        has_median=True,
        sidewalk="no",
    )
    seg.classification = "main"
    layers, _ = build_road_geometry([seg])
    assert "MEDIANS" in layers
    assert len(layers["MEDIANS"]) >= 1


def test_mixed_road_types():
    """Mix of road types processes without errors."""
    segments = [
        _make_segment(name="Residential", highway_type="residential", width=6.0, lanes=2, y_offset=0),
        _make_segment(name="Primary", highway_type="primary", width=6.5, lanes=2, y_offset=200),
        _make_segment(name="Service", highway_type="service", width=3.0, lanes=1, sidewalk="no", y_offset=400),
    ]
    layers, warnings = build_road_geometry(segments)
    assert len(warnings) == 0
    assert len(layers["CENTERLINES"]) == 3
    assert len(layers["ROAD_EDGES"]) == 6  # 2 per road
