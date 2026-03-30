import pytest
from shapely.geometry import LineString, Polygon
from app.services.osm_parser import RoadSegment as ParsedRoad
from app.services.geometry.projection import ProjectionHelper
from app.services.geometry.centerlines import build_centerlines, clip_centerlines
from app.services.geometry.models import RoadSegment


@pytest.fixture
def proj():
    return ProjectionHelper(-73.98, 40.75)


@pytest.fixture
def boundary(proj):
    coords = [[-73.995, 40.748], [-73.975, 40.748], [-73.975, 40.758], [-73.995, 40.758]]
    return proj.transform_polygon(coords)


def _make_parsed_road(way_id=1, nodes=None, **kwargs):
    if nodes is None:
        nodes = [
            {"lat": 40.750, "lon": -73.990},
            {"lat": 40.751, "lon": -73.990},
            {"lat": 40.752, "lon": -73.990},
            {"lat": 40.753, "lon": -73.990},
            {"lat": 40.754, "lon": -73.990},
        ]
    defaults = dict(
        way_id=way_id, name="Test St", highway_type="residential",
        classification="local", width_m=6.0, lanes=2, lane_width_m=3.0,
        oneway=False, sidewalk="both", has_median=False, nodes=nodes,
    )
    defaults.update(kwargs)
    return ParsedRoad(**defaults)


def test_build_centerlines_basic(proj):
    parsed = [_make_parsed_road()]
    segments = build_centerlines(parsed, proj)
    assert len(segments) == 1
    seg = segments[0]
    assert isinstance(seg.centerline, LineString)
    assert len(seg.centerline.coords) == 5
    assert seg.name == "Test St"
    assert seg.width_m == 6.0


def test_build_centerlines_utm_coords(proj):
    parsed = [_make_parsed_road()]
    segments = build_centerlines(parsed, proj)
    coords = list(segments[0].centerline.coords)
    for x, y in coords:
        assert x > 100_000  # UTM easting
        assert y > 1_000_000  # UTM northing


def test_build_centerlines_skips_single_node(proj):
    parsed = [_make_parsed_road(nodes=[{"lat": 40.75, "lon": -73.99}])]
    segments = build_centerlines(parsed, proj)
    assert len(segments) == 0


def test_build_centerlines_preserves_attributes(proj):
    parsed = [_make_parsed_road(name="Main Ave", highway_type="primary", width_m=13.0, lanes=4)]
    segments = build_centerlines(parsed, proj)
    seg = segments[0]
    assert seg.name == "Main Ave"
    assert seg.highway_type == "primary"
    assert seg.width_m == 13.0
    assert seg.lanes == 4


def test_clip_fully_inside(proj, boundary):
    """Road fully inside polygon is unchanged."""
    parsed = [_make_parsed_road()]
    segments = build_centerlines(parsed, proj)
    clipped = clip_centerlines(segments, boundary)
    assert len(clipped) == 1
    assert abs(clipped[0].centerline.length - segments[0].centerline.length) < 1.0


def test_clip_fully_outside(proj, boundary):
    """Road fully outside polygon is excluded."""
    nodes = [
        {"lat": 40.700, "lon": -73.900},
        {"lat": 40.701, "lon": -73.900},
    ]
    parsed = [_make_parsed_road(nodes=nodes)]
    segments = build_centerlines(parsed, proj)
    clipped = clip_centerlines(segments, boundary)
    assert len(clipped) == 0


def test_clip_crossing_boundary(proj, boundary):
    """Road crossing boundary is clipped."""
    nodes = [
        {"lat": 40.745, "lon": -73.990},  # outside
        {"lat": 40.750, "lon": -73.990},  # inside
        {"lat": 40.755, "lon": -73.990},  # inside
        {"lat": 40.760, "lon": -73.990},  # outside
    ]
    parsed = [_make_parsed_road(nodes=nodes)]
    segments = build_centerlines(parsed, proj)
    clipped = clip_centerlines(segments, boundary)
    assert len(clipped) >= 1
    # Clipped should be shorter than original
    assert clipped[0].centerline.length < segments[0].centerline.length


def test_clip_preserves_attributes(proj, boundary):
    """Clipped segments keep original attributes."""
    parsed = [_make_parsed_road(name="Clip St", width_m=8.0)]
    segments = build_centerlines(parsed, proj)
    clipped = clip_centerlines(segments, boundary)
    assert clipped[0].name == "Clip St"
    assert clipped[0].width_m == 8.0


def test_road_segment_repr(proj):
    parsed = [_make_parsed_road(name="Repr St")]
    segments = build_centerlines(parsed, proj)
    r = repr(segments[0])
    assert "Repr St" in r
    assert "residential" in r
