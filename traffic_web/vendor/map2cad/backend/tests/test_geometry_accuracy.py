"""Geometry accuracy verification — verifies road widths, lane spacing,
sidewalk placement, and intersection polygons in generated DXF output."""

import ezdxf
from shapely.geometry import LineString, Point

from app.services.geometry.models import RoadSegment
from app.services.geometry.road_edges import generate_road_edges
from app.services.geometry.lane_markings import generate_lane_markings
from app.services.geometry.road_builder import build_road_geometry
from app.services.geometry.intersections import (
    detect_intersections,
    generate_intersection_polygons,
    apply_turning_radii,
)
from app.services.dxf_generator import generate_dxf


def _seg(name, centerline, width=6.0, lanes=2, lane_width=3.0,
         highway_type="residential", oneway=False, sidewalk="both",
         has_median=False, classification="local"):
    return RoadSegment(
        centerline=centerline,
        name=name,
        highway_type=highway_type,
        classification=classification,
        width_m=width,
        lanes=lanes,
        lane_width_m=lane_width,
        oneway=oneway,
        sidewalk=sidewalk,
        has_median=has_median,
    )


class TestRoadWidthAccuracy:
    def test_residential_6m(self):
        seg = _seg("Test Rd", LineString([(0, 0), (0, 200)]), width=6.0)
        left, right = generate_road_edges(seg)
        measured = abs(left.coords[0][0] - right.coords[0][0])
        assert abs(measured - 6.0) < 0.1, f"Expected 6.0m, got {measured:.2f}m"

    def test_primary_6_5m(self):
        seg = _seg("Primary", LineString([(0, 0), (0, 200)]),
                   width=6.5, highway_type="primary", classification="main")
        left, right = generate_road_edges(seg)
        measured = abs(left.coords[0][0] - right.coords[0][0])
        assert abs(measured - 6.5) < 0.1, f"Expected 6.5m, got {measured:.2f}m"

    def test_service_3m(self):
        seg = _seg("Service", LineString([(0, 0), (0, 100)]),
                   width=3.0, lanes=1, lane_width=3.0,
                   highway_type="service", sidewalk="no")
        left, right = generate_road_edges(seg)
        measured = abs(left.coords[0][0] - right.coords[0][0])
        assert abs(measured - 3.0) < 0.1, f"Expected 3.0m, got {measured:.2f}m"


class TestLaneMarkingSpacing:
    def test_two_lane_center_marking(self):
        seg = _seg("2Lane", LineString([(0, 0), (0, 200)]),
                   width=6.0, lanes=2, lane_width=3.0)
        markings = generate_lane_markings(seg)
        assert len(markings) >= 1
        center_x = markings[0][0].coords[0][0]
        assert abs(center_x - 0.0) < 0.1, f"Center marking at {center_x}, expected 0"

    def test_four_lane_three_dividers(self):
        seg = _seg("4Lane", LineString([(0, 0), (0, 200)]),
                   width=12.0, lanes=4, lane_width=3.0)
        markings = generate_lane_markings(seg)
        assert len(markings) == 3, f"Expected 3 dividers, got {len(markings)}"
        xs = sorted([m[0].coords[0][0] for m in markings])
        for actual, expected in zip(xs, [-3.0, 0.0, 3.0]):
            assert abs(actual - expected) < 0.2, f"Marking at {actual}, expected {expected}"


class TestSidewalkAndCurbViaPipeline:
    def test_residential_has_sidewalks_and_curbs(self):
        seg = _seg("SidewalkRd", LineString([(0, 0), (0, 200)]),
                   width=6.0, sidewalk="both")
        layers, _ = build_road_geometry([seg], None)
        assert len(layers.get("SIDEWALKS", [])) == 2
        assert len(layers.get("CURBS", [])) >= 2
        for sw, _ in layers["SIDEWALKS"]:
            x = abs(sw.coords[0][0])
            assert x > 3.0, f"Sidewalk inside road edge at x={x}"

    def test_motorway_no_sidewalks(self):
        seg = _seg("Motorway", LineString([(0, 0), (0, 500)]),
                   width=10.5, lanes=3, lane_width=3.5,
                   highway_type="motorway", sidewalk="no", classification="main")
        layers, _ = build_road_geometry([seg], None)
        assert len(layers.get("SIDEWALKS", [])) == 0

    def test_curbs_between_edge_and_sidewalk(self):
        seg = _seg("CurbRd", LineString([(0, 0), (0, 200)]),
                   width=6.0, sidewalk="both")
        layers, _ = build_road_geometry([seg], None)
        for curb, _ in layers.get("CURBS", []):
            cx = abs(curb.coords[0][0])
            assert cx > 3.0, f"Curb inside road edge: {cx}"
            assert cx < 3.5, f"Curb too far from road edge: {cx}"


class TestIntersectionPolygon:
    def test_cross_intersection_detected(self):
        seg_h = _seg("Horiz", LineString([(-100, 0), (100, 0)]), width=6.0)
        seg_v = _seg("Vert", LineString([(0, -100), (0, 100)]), width=6.0)

        ixs = detect_intersections([seg_h, seg_v])
        assert len(ixs) >= 1
        ixs = generate_intersection_polygons(ixs, [seg_h, seg_v])
        ixs = apply_turning_radii(ixs)
        assert len(ixs) >= 1
        for ix in ixs:
            assert ix.polygon.contains(Point(0, 0))
            bounds = ix.polygon.bounds
            assert bounds[0] < -2 and bounds[2] > 2
            assert bounds[1] < -2 and bounds[3] > 2


class TestFullPipelineDXFAccuracy:
    def test_road_measurements_in_dxf(self, tmp_path):
        seg = _seg("Main St", LineString([(0, 0), (0, 300)]),
                   width=6.0, lanes=2, lane_width=3.0, sidewalk="both")
        layers, _ = build_road_geometry([seg], None)
        filepath = generate_dxf(layers=layers, boundary=None, output_dir=str(tmp_path))
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        counts = {}
        for e in msp:
            counts[e.dxf.layer] = counts.get(e.dxf.layer, 0) + 1

        assert counts.get("ROAD_EDGES", 0) == 2
        assert counts.get("CENTERLINES", 0) == 1
        assert counts.get("LANE_MARKINGS", 0) >= 1
        assert counts.get("CURBS", 0) >= 2
        assert counts.get("SIDEWALKS", 0) == 2

        edges = [e for e in msp if e.dxf.layer == "ROAD_EDGES"]
        pts0 = list(edges[0].get_points())
        pts1 = list(edges[1].get_points())
        width = abs(pts0[0][0] - pts1[0][0])
        assert abs(width - 6.0) < 0.15, f"DXF road width {width:.2f}m, expected 6.0m"

        texts = [e for e in msp if e.dxf.layer == "ROAD_NAMES"]
        assert len(texts) >= 1
        assert any(t.dxf.text == "Main St" for t in texts)
