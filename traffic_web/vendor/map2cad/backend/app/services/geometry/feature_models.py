"""Data models for non-road OSM features."""

from dataclasses import dataclass, field
from shapely.geometry import LineString, Point, Polygon


@dataclass
class BuildingFootprint:
    way_id: int
    polygon: Polygon
    name: str = ""
    building_type: str = "yes"  # yes, residential, commercial, industrial, etc.
    tags: dict = field(default_factory=dict)


@dataclass
class LandUseArea:
    way_id: int
    polygon: Polygon
    name: str = ""
    landuse_type: str = "residential"  # park, water, industrial, commercial, residential
    tags: dict = field(default_factory=dict)


@dataclass
class RailwayLine:
    way_id: int
    centerline: LineString
    name: str = ""
    railway_type: str = "rail"  # rail, tram, light_rail, subway
    tags: dict = field(default_factory=dict)


@dataclass
class ParkingArea:
    element_id: int
    polygon: Polygon | None = None
    point: Point | None = None
    parking_type: str = "surface"  # surface, multi-storey, underground, street
    name: str = ""
    capacity: int | None = None
    tags: dict = field(default_factory=dict)


@dataclass
class PointFeature:
    node_id: int
    point: Point
    feature_type: str = "tree"  # traffic_signal, tree, bench, street_lamp, manhole
    tags: dict = field(default_factory=dict)


@dataclass
class CyclewayLine:
    way_id: int
    centerline: LineString
    name: str = ""
    cycleway_type: str = "lane"  # lane, track, shared, path
    tags: dict = field(default_factory=dict)


@dataclass
class UtilityFeature:
    element_id: int
    geometry: LineString | Point
    utility_type: str = "manhole"  # power_line, minor_power_line, manhole
    tags: dict = field(default_factory=dict)
