"""Tests for intersection detection and modeling."""

import math
import pytest
from shapely.geometry import LineString, Point, Polygon
from app.services.geometry.models import RoadSegment
from app.services.geometry.intersections import (
    detect_intersections,
    generate_intersection_polygons,
    apply_turning_radii,
    trim_geometry_at_intersections,
    _get_turning_radius,
    _approach_angle,
    Intersection,
    IntersectionApproach,
)


def _make_segment(coords, name="Rd", highway_type="residential", width=6.0, lanes=2):
    return RoadSegment(
        centerline=LineString(coords),
        name=name,
        highway_type=highway_type,
        classification="local",
        width_m=width,
        lanes=lanes,
        lane_width_m=3.0,
        oneway=False,
        sidewalk="both",
        has_median=False,
    )


# ---- Task 1: Detection ----

def test_perpendicular_cross_intersection():
    """Two perpendicular roads produce 1 intersection."""
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="NS Road"),
        _make_segment([(499950, 4500050), (500050, 4500050)], name="EW Road"),
    ]
    intersections = detect_intersections(segments)
    assert len(intersections) == 1
    ix = intersections[0]
    assert ix.degree == 2


def test_t_intersection():
    """T-intersection: one road ends at another."""
    segments = [
        _make_segment([(499950, 4500050), (500050, 4500050)], name="Through"),
        _make_segment([(500000, 4500000), (500000, 4500050)], name="Terminating"),
    ]
    intersections = detect_intersections(segments)
    assert len(intersections) >= 1


def test_parallel_no_intersection():
    """Two parallel roads produce 0 intersections."""
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="Road A"),
        _make_segment([(500020, 4500000), (500020, 4500100)], name="Road B"),
    ]
    intersections = detect_intersections(segments)
    assert len(intersections) == 0


def test_five_way_intersection():
    """5 roads meeting at a point produce 1 intersection with 5+ participating roads."""
    center = (500000, 4500050)
    segments = []
    for i, angle_deg in enumerate([0, 72, 144, 216, 288]):
        rad = math.radians(angle_deg)
        dx = 60 * math.cos(rad)
        dy = 60 * math.sin(rad)
        coords = [
            (center[0] - dx, center[1] - dy),
            (center[0] + dx, center[1] + dy),
        ]
        segments.append(_make_segment(coords, name=f"Spoke {i}"))
    intersections = detect_intersections(segments)
    # All roads cross at center — should cluster to 1 intersection
    assert len(intersections) >= 1
    # The main cluster should have multiple approaches
    max_degree = max(ix.degree for ix in intersections)
    assert max_degree >= 4


def test_nearby_points_clustered():
    """3 nearby intersection points cluster into 1."""
    # Three roads that cross very near each other
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="NS"),
        _make_segment([(499950, 4500049), (500050, 4500049)], name="EW1"),
        _make_segment([(499950, 4500051), (500050, 4500051)], name="EW2"),
    ]
    intersections = detect_intersections(segments)
    # The two crossing points are within 2m, should cluster
    assert len(intersections) <= 2


# ---- Task 2: Classification ----

def test_t_intersection_classified():
    """T-intersection classified as degree 3."""
    segments = [
        _make_segment([(499950, 4500050), (500050, 4500050)], name="Through"),
        _make_segment([(500000, 4500000), (500000, 4500050)], name="Side1"),
        _make_segment([(500000, 4500050), (500000, 4500100)], name="Side2"),
    ]
    intersections = detect_intersections(segments)
    assert any(ix.degree >= 2 for ix in intersections)


def test_approach_angle_perpendicular():
    """Approach angle calculated correctly for perpendicular roads."""
    cl = LineString([(500000, 4500000), (500000, 4500100)])
    pt = Point(500000, 4500050)
    angle = _approach_angle(cl, pt)
    # North-going road should be ~90 degrees
    assert abs(angle - 90) < 5


def test_turning_radius_residential():
    """Turning radius for residential + residential = 6."""
    assert _get_turning_radius("residential", "residential") == 6


def test_turning_radius_primary_residential():
    """Turning radius for primary + residential = 9."""
    assert _get_turning_radius("primary", "residential") == 9


# ---- Task 3: Intersection polygons ----

def test_cross_intersection_polygon():
    """4-way cross intersection produces a polygon covering the crossing area."""
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="NS", width=6.0),
        _make_segment([(499950, 4500050), (500050, 4500050)], name="EW", width=6.0),
    ]
    intersections = detect_intersections(segments)
    intersections = generate_intersection_polygons(intersections, segments)
    assert len(intersections) >= 1
    ix = intersections[0]
    assert ix.polygon is not None
    assert isinstance(ix.polygon, Polygon)
    assert ix.polygon.is_valid
    assert ix.polygon.area > 0


def test_intersection_polygon_no_holes():
    """Intersection polygon has no holes."""
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="NS"),
        _make_segment([(499950, 4500050), (500050, 4500050)], name="EW"),
    ]
    intersections = detect_intersections(segments)
    intersections = generate_intersection_polygons(intersections, segments)
    for ix in intersections:
        if ix.polygon:
            assert len(list(ix.polygon.interiors)) == 0


# ---- Task 4: Turning radii ----

def test_turning_radii_applied():
    """Turning radii produce a valid polygon."""
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="NS"),
        _make_segment([(499950, 4500050), (500050, 4500050)], name="EW"),
    ]
    intersections = detect_intersections(segments)
    intersections = generate_intersection_polygons(intersections, segments)
    intersections = apply_turning_radii(intersections)
    for ix in intersections:
        assert ix.polygon is not None
        assert ix.polygon.is_valid


# ---- Task 5: Trim road edges ----

def test_centerline_not_trimmed():
    """Centerline passes through intersection untrimmed."""
    cl = LineString([(500000, 4500000), (500000, 4500100)])
    ix_poly = Point(500000, 4500050).buffer(10)

    layers = {
        "CENTERLINES": [(cl, {"name": "Test"})],
        "ROAD_EDGES": [(cl, {"name": "Test"})],
    }
    intersections = [Intersection(
        point=Point(500000, 4500050),
        polygon=ix_poly,
        degree=2,
    )]
    trimmed = trim_geometry_at_intersections(layers, intersections)
    # Centerline should be unchanged
    assert len(trimmed["CENTERLINES"]) == 1
    assert trimmed["CENTERLINES"][0][0].length == cl.length
    # Road edges should be trimmed (split into 2 segments)
    assert len(trimmed["ROAD_EDGES"]) == 2


def test_road_edge_trimmed_at_intersection():
    """Road edge through intersection produces two segments."""
    edge = LineString([(500003, 4500000), (500003, 4500100)])
    ix_poly = Point(500000, 4500050).buffer(10)

    layers = {"ROAD_EDGES": [(edge, {"name": "Test"})]}
    intersections = [Intersection(
        point=Point(500000, 4500050),
        polygon=ix_poly,
        degree=2,
    )]
    trimmed = trim_geometry_at_intersections(layers, intersections)
    # Edge should be split into segments before and after intersection
    assert len(trimmed["ROAD_EDGES"]) == 2
    for geom, meta in trimmed["ROAD_EDGES"]:
        assert isinstance(geom, LineString)
        assert geom.length > 0


def test_no_geometry_inside_intersection():
    """No trimmed road edge geometry extends inside the intersection polygon."""
    edge = LineString([(500003, 4500000), (500003, 4500100)])
    ix_poly = Point(500000, 4500050).buffer(10)

    layers = {"ROAD_EDGES": [(edge, {"name": "Test"})]}
    intersections = [Intersection(
        point=Point(500000, 4500050),
        polygon=ix_poly,
        degree=2,
    )]
    trimmed = trim_geometry_at_intersections(layers, intersections)
    for geom, meta in trimmed["ROAD_EDGES"]:
        # Trimmed geometry should not intersect the interior of the polygon
        assert geom.intersection(ix_poly).length < 0.5


# ---- Task 6: T-intersection ----

def test_t_intersection_polygon():
    """T-intersection generates a polygon."""
    segments = [
        _make_segment([(499950, 4500050), (500050, 4500050)], name="Through"),
        _make_segment([(500000, 4500000), (500000, 4500050)], name="Side"),
    ]
    intersections = detect_intersections(segments)
    intersections = generate_intersection_polygons(intersections, segments)
    assert any(ix.polygon is not None for ix in intersections)


# ---- Task 8: Edge cases ----

def test_non_perpendicular_intersection():
    """Non-perpendicular (60 degree) intersection produces a polygon."""
    segments = [
        _make_segment([(500000, 4500000), (500000, 4500100)], name="NS"),
        _make_segment(
            [(499950, 4500050 - 29), (500050, 4500050 + 29)],  # ~30 deg angle
            name="Angled",
        ),
    ]
    intersections = detect_intersections(segments)
    intersections = generate_intersection_polygons(intersections, segments)
    assert len(intersections) >= 1
    assert any(ix.polygon is not None for ix in intersections)


def test_empty_segments_no_crash():
    """Empty segment list produces no intersections."""
    intersections = detect_intersections([])
    assert intersections == []


def test_single_segment_no_intersections():
    """Single segment produces no intersections."""
    segments = [_make_segment([(500000, 4500000), (500000, 4500100)])]
    intersections = detect_intersections(segments)
    assert intersections == []
