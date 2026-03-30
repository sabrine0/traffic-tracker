"""DXF readback integration tests — verify real-world scale and coordinate accuracy."""

import os
import ezdxf
from shapely.geometry import LineString, Polygon, Point

from app.services.dxf_generator import (
    create_dxf_document,
    create_layers,
    write_line_layers,
    write_intersections,
    write_boundary,
    generate_dxf,
    LAYER_DEFS,
)


class FakeIntersection:
    def __init__(self, polygon):
        self.polygon = polygon


def _make_road_layers(width=6.0, length=200.0):
    """Create geometry layers for a single road with known width."""
    half = width / 2
    return {
        "ROAD_EDGES": [
            (LineString([(half, 0), (half, length)]), {"name": "TestRd", "highway_type": "residential"}),
            (LineString([(-half, 0), (-half, length)]), {"name": "TestRd", "highway_type": "residential"}),
        ],
        "CENTERLINES": [
            (LineString([(0, 0), (0, length)]), {"name": "TestRd", "highway_type": "residential"}),
        ],
        "LANE_MARKINGS": [],
        "CURBS": [],
        "SIDEWALKS": [],
        "MEDIANS": [],
    }


def test_road_width_matches_input(tmp_path):
    """Road edges in generated DXF should be exactly <width> meters apart."""
    width = 6.0
    layers = _make_road_layers(width=width, length=100.0)
    filepath = generate_dxf(layers=layers, boundary=None, output_dir=str(tmp_path))

    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    edges = [e for e in msp if e.dxf.layer == "ROAD_EDGES"]
    assert len(edges) == 2

    # Get first vertex of each edge
    pts0 = list(edges[0].get_points())
    pts1 = list(edges[1].get_points())
    x0 = pts0[0][0]
    x1 = pts1[0][0]
    measured_width = abs(x1 - x0)
    assert abs(measured_width - width) < 0.01


def test_road_length_matches_input(tmp_path):
    """Road centerline in DXF should have correct length."""
    length = 200.0
    layers = _make_road_layers(width=6.0, length=length)
    filepath = generate_dxf(layers=layers, boundary=None, output_dir=str(tmp_path))

    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    centerlines = [e for e in msp if e.dxf.layer == "CENTERLINES"]
    assert len(centerlines) == 1

    pts = list(centerlines[0].get_points())
    dy = abs(pts[-1][1] - pts[0][1])
    assert abs(dy - length) < 0.01


def test_dxf_units_are_meters(tmp_path):
    """DXF INSUNITS should be 6 (meters)."""
    layers = _make_road_layers()
    filepath = generate_dxf(layers=layers, boundary=None, output_dir=str(tmp_path))
    doc = ezdxf.readfile(filepath)
    assert doc.header["$INSUNITS"] == 6


def test_boundary_coordinates_preserved(tmp_path):
    """Boundary polygon coordinates should match input exactly."""
    layers = _make_road_layers()
    boundary = Polygon([(0, 0), (100, 0), (100, 200), (0, 200)])
    filepath = generate_dxf(layers=layers, boundary=boundary, output_dir=str(tmp_path))

    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    boundaries = [e for e in msp if e.dxf.layer == "BOUNDARY"]
    assert len(boundaries) == 1

    pts = list(boundaries[0].get_points())
    # Should have 4 vertices (closed polyline)
    assert len(pts) >= 4
    xs = [p[0] for p in pts[:4]]
    ys = [p[1] for p in pts[:4]]
    assert min(xs) < 1
    assert max(xs) > 99
    assert min(ys) < 1
    assert max(ys) > 199


def test_all_layers_present_in_readback(tmp_path):
    """DXF readback should have all 9 defined layers."""
    layers = _make_road_layers()
    boundary = Polygon([(0, 0), (100, 0), (100, 200), (0, 200)])
    ix = FakeIntersection(Point(50, 100).buffer(5))
    filepath = generate_dxf(layers=layers, intersections=[ix], boundary=boundary, output_dir=str(tmp_path))

    doc = ezdxf.readfile(filepath)
    for name in LAYER_DEFS:
        assert name in doc.layers, f"Layer {name} missing from DXF"


def test_layer_properties_preserved(tmp_path):
    """Layer colors and linetypes should survive save/reload."""
    layers = _make_road_layers()
    filepath = generate_dxf(layers=layers, boundary=None, output_dir=str(tmp_path))

    doc = ezdxf.readfile(filepath)
    for name, props in LAYER_DEFS.items():
        layer = doc.layers.get(name)
        assert layer.color == props["color"], f"{name} color mismatch"
        assert layer.dxf.linetype == props["linetype"], f"{name} linetype mismatch"
