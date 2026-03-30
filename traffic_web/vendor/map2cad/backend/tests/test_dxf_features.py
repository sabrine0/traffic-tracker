"""Unit tests for DXF polygon and point layer output."""

import ezdxf
from shapely.geometry import Point, Polygon

from app.services.dxf_generator import (
    LAYER_DEFS,
    create_dxf_document,
    create_layers,
    write_polygon_layers,
    write_point_layers,
)


def _doc():
    doc = create_dxf_document()
    create_layers(doc)
    return doc


class TestNewLayerDefinitions:
    def test_all_19_layers_exist(self):
        doc = _doc()
        for name in LAYER_DEFS:
            assert name in doc.layers

    def test_feature_layers_present(self):
        feature_layers = [
            "BUILDINGS", "LANDUSE_PARK", "LANDUSE_WATER", "LANDUSE_ZONES",
            "RAILWAYS", "PARKING", "TRAFFIC_SIGNALS", "STREET_FURNITURE",
            "CYCLEWAYS", "UTILITIES",
        ]
        doc = _doc()
        for name in feature_layers:
            assert name in doc.layers
            assert name in LAYER_DEFS

    def test_layer_colors_distinct(self):
        """Each layer should have a unique color (except ROAD_EDGES/ROAD_NAMES share 7)."""
        colors = {}
        for name, props in LAYER_DEFS.items():
            c = props["color"]
            if c in colors:
                # Only allow known duplicates
                assert {name, colors[c]} <= {"ROAD_EDGES", "ROAD_NAMES"}, \
                    f"Color {c} used by both {colors[c]} and {name}"
            colors[c] = name


class TestWritePolygonLayers:
    def test_writes_closed_polylines(self):
        doc = _doc()
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        layers = {"BUILDINGS": [(poly, {"name": "Bldg"})]}
        counts = write_polygon_layers(doc, layers)
        assert counts["BUILDINGS"] >= 1

        msp = doc.modelspace()
        entities = [e for e in msp if e.dxf.layer == "BUILDINGS"]
        assert len(entities) >= 1

    def test_hatched_landuse_park(self):
        doc = _doc()
        poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        layers = {"LANDUSE_PARK": [(poly, {"name": "Park"})]}
        counts = write_polygon_layers(doc, layers)
        # 1 polyline + 1 hatch = 2
        assert counts["LANDUSE_PARK"] >= 2

    def test_hatched_landuse_water(self):
        doc = _doc()
        poly = Polygon([(0, 0), (50, 0), (50, 50), (0, 50)])
        layers = {"LANDUSE_WATER": [(poly, {"name": "Lake"})]}
        counts = write_polygon_layers(doc, layers)
        assert counts["LANDUSE_WATER"] >= 2

    def test_buildings_no_hatch(self):
        doc = _doc()
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        layers = {"BUILDINGS": [(poly, {})]}
        counts = write_polygon_layers(doc, layers)
        # Buildings: outline only, no hatch
        assert counts["BUILDINGS"] == 1

    def test_skips_empty_polygon(self):
        doc = _doc()
        poly = Polygon()  # empty
        layers = {"BUILDINGS": [(poly, {})]}
        counts = write_polygon_layers(doc, layers)
        assert counts["BUILDINGS"] == 0

    def test_skips_unknown_layer(self):
        doc = _doc()
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        layers = {"UNKNOWN_LAYER": [(poly, {})]}
        counts = write_polygon_layers(doc, layers)
        assert "UNKNOWN_LAYER" not in counts


class TestWritePointLayers:
    def test_writes_circles(self):
        doc = _doc()
        pt = Point(50, 50)
        layers = {"TRAFFIC_SIGNALS": [(pt, {"feature_type": "traffic_signal"})]}
        counts = write_point_layers(doc, layers)
        assert counts["TRAFFIC_SIGNALS"] == 1

        msp = doc.modelspace()
        circles = [e for e in msp if e.dxf.layer == "TRAFFIC_SIGNALS" and e.dxftype() == "CIRCLE"]
        assert len(circles) == 1
        assert circles[0].dxf.radius == 1.0  # traffic_signal radius

    def test_tree_radius(self):
        doc = _doc()
        pt = Point(50, 50)
        layers = {"STREET_FURNITURE": [(pt, {"feature_type": "tree"})]}
        counts = write_point_layers(doc, layers)
        assert counts["STREET_FURNITURE"] == 1

        msp = doc.modelspace()
        circles = [e for e in msp if e.dxf.layer == "STREET_FURNITURE"]
        assert circles[0].dxf.radius == 0.5

    def test_default_radius(self):
        doc = _doc()
        pt = Point(50, 50)
        layers = {"UTILITIES": [(pt, {"feature_type": "unknown_type"})]}
        counts = write_point_layers(doc, layers)
        assert counts["UTILITIES"] == 1

        msp = doc.modelspace()
        circles = [e for e in msp if e.dxf.layer == "UTILITIES"]
        assert circles[0].dxf.radius == 0.4  # default

    def test_skips_empty_point(self):
        doc = _doc()
        pt = Point()  # empty
        layers = {"TRAFFIC_SIGNALS": [(pt, {})]}
        counts = write_point_layers(doc, layers)
        assert counts["TRAFFIC_SIGNALS"] == 0

    def test_multiple_points(self):
        doc = _doc()
        layers = {
            "STREET_FURNITURE": [
                (Point(10, 10), {"feature_type": "tree"}),
                (Point(20, 20), {"feature_type": "bench"}),
                (Point(30, 30), {"feature_type": "street_lamp"}),
            ]
        }
        counts = write_point_layers(doc, layers)
        assert counts["STREET_FURNITURE"] == 3
