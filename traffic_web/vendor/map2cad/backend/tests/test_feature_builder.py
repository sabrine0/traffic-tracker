"""Unit tests for feature_builder module."""

from shapely.geometry import LineString, Point, Polygon

from app.services.geometry.feature_models import (
    BuildingFootprint,
    CyclewayLine,
    LandUseArea,
    ParkingArea,
    PointFeature,
    RailwayLine,
    UtilityFeature,
)
from app.services.geometry.feature_builder import build_feature_geometry


def _poly(x=0, y=0, size=10):
    return Polygon([(x, y), (x+size, y), (x+size, y+size), (x, y+size)])


def _line(x1=0, y1=0, x2=100, y2=0):
    return LineString([(x1, y1), (x2, y2)])


def _point(x=50, y=50):
    return Point(x, y)


class TestBuildFeatureGeometry:
    def test_buildings_to_polygon_layer(self):
        buildings = [BuildingFootprint(1, _poly(), "House", "residential")]
        lines, polys, points, warnings = build_feature_geometry(buildings=buildings)
        assert "BUILDINGS" in polys
        assert len(polys["BUILDINGS"]) == 1

    def test_landuse_park_to_correct_layer(self):
        areas = [LandUseArea(1, _poly(), "Park", "park")]
        _, polys, _, _ = build_feature_geometry(landuse=areas)
        assert "LANDUSE_PARK" in polys
        assert len(polys["LANDUSE_PARK"]) == 1

    def test_landuse_water_to_correct_layer(self):
        areas = [LandUseArea(1, _poly(), "Lake", "water")]
        _, polys, _, _ = build_feature_geometry(landuse=areas)
        assert "LANDUSE_WATER" in polys

    def test_landuse_zone_to_correct_layer(self):
        areas = [LandUseArea(1, _poly(), "Factory", "industrial")]
        _, polys, _, _ = build_feature_geometry(landuse=areas)
        assert "LANDUSE_ZONES" in polys

    def test_railway_rail_produces_dual_lines(self):
        railways = [RailwayLine(1, _line(), "Metro", "rail")]
        lines, _, _, _ = build_feature_geometry(railways=railways)
        assert "RAILWAYS" in lines
        # Dual rail = 2 offset lines
        assert len(lines["RAILWAYS"]) == 2

    def test_railway_tram_produces_single_line(self):
        railways = [RailwayLine(1, _line(), "Tram", "tram")]
        lines, _, _, _ = build_feature_geometry(railways=railways)
        assert "RAILWAYS" in lines
        assert len(lines["RAILWAYS"]) == 1

    def test_parking_lot_to_polygon(self):
        parking = [ParkingArea(1, polygon=_poly(), parking_type="surface")]
        _, polys, _, _ = build_feature_geometry(parking=parking)
        assert "PARKING" in polys

    def test_parking_space_to_point(self):
        parking = [ParkingArea(1, point=_point(), parking_type="street")]
        _, _, points, _ = build_feature_geometry(parking=parking)
        assert "PARKING" in points

    def test_traffic_signals_to_point_layer(self):
        pts = [PointFeature(1, _point(), "traffic_signal")]
        _, _, points, _ = build_feature_geometry(points=pts)
        assert "TRAFFIC_SIGNALS" in points
        assert len(points["TRAFFIC_SIGNALS"]) == 1

    def test_street_furniture_to_point_layer(self):
        pts = [
            PointFeature(1, _point(10, 10), "tree"),
            PointFeature(2, _point(20, 20), "bench"),
            PointFeature(3, _point(30, 30), "street_lamp"),
        ]
        _, _, points, _ = build_feature_geometry(points=pts)
        assert "STREET_FURNITURE" in points
        assert len(points["STREET_FURNITURE"]) == 3

    def test_cycleways_to_line_layer(self):
        cycles = [CyclewayLine(1, _line(), "Bike Lane", "lane")]
        lines, _, _, _ = build_feature_geometry(cycleways=cycles)
        assert "CYCLEWAYS" in lines
        assert len(lines["CYCLEWAYS"]) == 1

    def test_utility_lines_and_points(self):
        utils = [
            UtilityFeature(1, _line(), "power_line"),
            UtilityFeature(2, _point(), "manhole"),
        ]
        lines, _, points, _ = build_feature_geometry(utilities=utils)
        assert "UTILITIES" in lines
        assert "UTILITIES" in points

    def test_empty_inputs_return_empty(self):
        lines, polys, points, warnings = build_feature_geometry()
        assert lines == {}
        assert polys == {}
        assert points == {}
        assert warnings == []
