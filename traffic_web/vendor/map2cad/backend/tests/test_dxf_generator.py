"""Tests for DXF generation pipeline."""

import os
import pytest
import ezdxf
from shapely.geometry import LineString, Polygon, Point

from app.services.dxf_generator import (
    create_dxf_document,
    create_layers,
    write_line_layers,
    write_intersections,
    write_road_names,
    write_boundary,
    generate_dxf,
    LAYER_DEFS,
)


@pytest.fixture
def doc():
    d = create_dxf_document()
    create_layers(d)
    return d


@pytest.fixture
def sample_layers():
    """Sample geometry layers for testing."""
    return {
        "ROAD_EDGES": [
            (LineString([(0, 0), (0, 100)]), {"name": "Edge1", "highway_type": "residential"}),
            (LineString([(6, 0), (6, 100)]), {"name": "Edge2", "highway_type": "residential"}),
        ],
        "CENTERLINES": [
            (LineString([(3, 0), (3, 100)]), {"name": "Main St", "highway_type": "residential"}),
            (LineString([(50, 0), (50, 100)]), {"name": "", "highway_type": "residential"}),
        ],
        "LANE_MARKINGS": [
            (LineString([(3, 0), (3, 100)]), {"name": "Main St", "linetype": "solid"}),
            (LineString([(1.5, 0), (1.5, 100)]), {"name": "Main St", "linetype": "dashed"}),
        ],
        "CURBS": [
            (LineString([(-0.15, 0), (-0.15, 100)]), {"name": "Curb", "highway_type": "residential"}),
        ],
        "SIDEWALKS": [
            (LineString([(-1.65, 0), (-1.65, 100)]), {"name": "SW", "highway_type": "residential"}),
        ],
        "MEDIANS": [
            (LineString([(20, 0), (20, 100)]), {"name": "Med", "highway_type": "motorway"}),
        ],
    }


class FakeIntersection:
    def __init__(self, polygon):
        self.polygon = polygon


# ---- Task 1: Document creation ----

def test_dxf_document_created():
    doc = create_dxf_document()
    assert doc is not None
    assert doc.modelspace() is not None


def test_insunits_is_meters():
    doc = create_dxf_document()
    assert doc.header["$INSUNITS"] == 6


def test_dashed_linetype_exists():
    doc = create_dxf_document()
    assert "DASHED" in doc.linetypes


def test_dashdot_linetype_exists():
    doc = create_dxf_document()
    assert "DASHDOT" in doc.linetypes


def test_save_and_reopen(tmp_path):
    doc = create_dxf_document()
    create_layers(doc)
    path = str(tmp_path / "test.dxf")
    doc.saveas(path)
    doc2 = ezdxf.readfile(path)
    assert doc2 is not None


# ---- Task 2: Layer creation ----

def test_all_9_layers_exist(doc):
    for name in LAYER_DEFS:
        assert name in doc.layers


def test_layer_colors(doc):
    for name, props in LAYER_DEFS.items():
        layer = doc.layers.get(name)
        assert layer.color == props["color"]


def test_layer_linetypes(doc):
    for name, props in LAYER_DEFS.items():
        layer = doc.layers.get(name)
        assert layer.dxf.linetype == props["linetype"]


def test_layer_lineweights(doc):
    for name, props in LAYER_DEFS.items():
        layer = doc.layers.get(name)
        assert layer.dxf.lineweight == props["lineweight"]


# ---- Task 3: Road edge polylines ----

def test_road_edges_written(doc, sample_layers):
    counts = write_line_layers(doc, sample_layers)
    assert counts["ROAD_EDGES"] == 2
    msp = doc.modelspace()
    edges = [e for e in msp if e.dxf.layer == "ROAD_EDGES"]
    assert len(edges) == 2


def test_polyline_vertex_count(doc, sample_layers):
    write_line_layers(doc, sample_layers)
    msp = doc.modelspace()
    edges = [e for e in msp if e.dxf.layer == "ROAD_EDGES"]
    for e in edges:
        # 2-point line -> 2 vertices
        assert len(list(e.get_points())) == 2


def test_coordinates_match(doc, sample_layers):
    write_line_layers(doc, sample_layers)
    msp = doc.modelspace()
    edges = [e for e in msp if e.dxf.layer == "ROAD_EDGES"]
    pts = list(edges[0].get_points())
    assert abs(pts[0][0] - 0.0) < 0.01
    assert abs(pts[0][1] - 0.0) < 0.01


# ---- Task 4: Other line layers ----

def test_centerlines_written(doc, sample_layers):
    counts = write_line_layers(doc, sample_layers)
    assert counts["CENTERLINES"] == 2


def test_lane_markings_linetypes(doc, sample_layers):
    write_line_layers(doc, sample_layers)
    msp = doc.modelspace()
    markings = [e for e in msp if e.dxf.layer == "LANE_MARKINGS"]
    linetypes = [e.dxf.linetype for e in markings]
    assert "CONTINUOUS" in linetypes  # solid center marking
    assert "DASHED" in linetypes  # dashed lane marking


def test_curbs_written(doc, sample_layers):
    counts = write_line_layers(doc, sample_layers)
    assert counts["CURBS"] == 1


def test_sidewalks_written(doc, sample_layers):
    counts = write_line_layers(doc, sample_layers)
    assert counts["SIDEWALKS"] == 1


def test_medians_written(doc, sample_layers):
    counts = write_line_layers(doc, sample_layers)
    assert counts["MEDIANS"] == 1


# ---- Task 5: Intersection polygons ----

def test_intersection_polylines(doc):
    poly = Point(50, 50).buffer(10)
    ixs = [FakeIntersection(poly)]
    count = write_intersections(doc, ixs)
    assert count >= 1  # polyline + optional hatch
    msp = doc.modelspace()
    ix_entities = [e for e in msp if e.dxf.layer == "INTERSECTIONS"]
    assert len(ix_entities) >= 1


def test_intersection_polyline_closed(doc):
    poly = Point(50, 50).buffer(10)
    ixs = [FakeIntersection(poly)]
    write_intersections(doc, ixs)
    msp = doc.modelspace()
    polys = [e for e in msp if e.dxf.layer == "INTERSECTIONS" and e.dxftype() == "LWPOLYLINE"]
    assert len(polys) >= 1
    assert polys[0].is_closed is True


# ---- Task 6: Road names ----

def test_named_roads_have_labels(doc, sample_layers):
    count = write_road_names(doc, sample_layers)
    assert count >= 1  # "Main St" should get a label
    msp = doc.modelspace()
    texts = [e for e in msp if e.dxf.layer == "ROAD_NAMES"]
    assert len(texts) >= 1


def test_unnamed_roads_no_labels(doc, sample_layers):
    write_road_names(doc, sample_layers)
    msp = doc.modelspace()
    texts = [e for e in msp if e.dxf.layer == "ROAD_NAMES"]
    for t in texts:
        assert t.dxf.text != ""


def test_text_on_correct_layer(doc, sample_layers):
    write_road_names(doc, sample_layers)
    msp = doc.modelspace()
    texts = [e for e in msp if e.dxftype() == "TEXT"]
    for t in texts:
        assert t.dxf.layer == "ROAD_NAMES"


# ---- Task 7: Boundary ----

def test_boundary_written(doc):
    boundary = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    count = write_boundary(doc, boundary)
    assert count == 1
    msp = doc.modelspace()
    boundary_entities = [e for e in msp if e.dxf.layer == "BOUNDARY"]
    assert len(boundary_entities) == 1


def test_boundary_is_closed(doc):
    boundary = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    write_boundary(doc, boundary)
    msp = doc.modelspace()
    polys = [e for e in msp if e.dxf.layer == "BOUNDARY"]
    assert polys[0].is_closed is True


def test_boundary_linetype(doc):
    boundary = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    write_boundary(doc, boundary)
    msp = doc.modelspace()
    polys = [e for e in msp if e.dxf.layer == "BOUNDARY"]
    assert polys[0].dxf.linetype == "DASHED"


def test_no_boundary_if_none(doc):
    count = write_boundary(doc, None)
    assert count == 0


# ---- Task 8: Full pipeline ----

def test_full_pipeline(tmp_path, sample_layers):
    boundary = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    poly = Point(50, 50).buffer(10)
    ixs = [FakeIntersection(poly)]

    filepath = generate_dxf(
        layers=sample_layers,
        intersections=ixs,
        boundary=boundary,
        output_dir=str(tmp_path),
    )

    assert os.path.exists(filepath)
    assert filepath.endswith(".dxf")

    # Read back and verify
    doc = ezdxf.readfile(filepath)
    assert doc is not None

    # All 9 layers should exist
    for name in LAYER_DEFS:
        assert name in doc.layers


def test_entity_counts(tmp_path, sample_layers):
    boundary = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    filepath = generate_dxf(
        layers=sample_layers,
        boundary=boundary,
        output_dir=str(tmp_path),
    )
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    # Count entities per layer
    layer_counts = {}
    for e in msp:
        layer = e.dxf.layer
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    assert layer_counts.get("ROAD_EDGES", 0) == 2
    assert layer_counts.get("CENTERLINES", 0) == 2
    assert layer_counts.get("LANE_MARKINGS", 0) == 2
    assert layer_counts.get("BOUNDARY", 0) == 1
