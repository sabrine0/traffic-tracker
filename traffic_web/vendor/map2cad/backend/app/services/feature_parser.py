"""Parse non-road OSM elements into typed feature models."""

import logging

from shapely.geometry import LineString, Point, Polygon
from shapely.validation import make_valid

from app.services.geometry.feature_models import (
    BuildingFootprint,
    CyclewayLine,
    LandUseArea,
    ParkingArea,
    PointFeature,
    RailwayLine,
    UtilityFeature,
)
from app.services.geometry.projection import ProjectionHelper

logger = logging.getLogger(__name__)


def _make_polygon(nodes: list[dict], proj: ProjectionHelper) -> Polygon | None:
    """Project nodes and create a valid Polygon, or None if degenerate."""
    if len(nodes) < 3:
        return None
    coords = [proj.to_utm(n["lon"], n["lat"]) for n in nodes]
    # Close the ring if needed
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = make_valid(poly)
        if poly.is_empty or not isinstance(poly, Polygon) or poly.area < 0.1:
            return None
        return poly
    except Exception:
        return None


def _make_linestring(nodes: list[dict], proj: ProjectionHelper) -> LineString | None:
    """Project nodes and create a LineString, or None if degenerate."""
    if len(nodes) < 2:
        return None
    coords = [proj.to_utm(n["lon"], n["lat"]) for n in nodes]
    try:
        line = LineString(coords)
        if line.is_empty or line.length < 0.1:
            return None
        return line
    except Exception:
        return None


def _make_point(node: dict, proj: ProjectionHelper) -> Point:
    """Project a node to a UTM Point."""
    x, y = proj.to_utm(node["lon"], node["lat"])
    return Point(x, y)


def parse_buildings(
    ways: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[BuildingFootprint]:
    """Parse ways with building=* tag into BuildingFootprint objects."""
    results = []
    for way in ways:
        tags = way.get("tags", {})
        if "building" not in tags:
            continue
        poly = _make_polygon(way["nodes"], proj)
        if poly is None:
            continue
        if boundary and not boundary.intersects(poly):
            continue
        if boundary:
            clipped = poly.intersection(boundary)
            if clipped.is_empty or not isinstance(clipped, Polygon):
                continue
            poly = clipped
        results.append(BuildingFootprint(
            way_id=way["id"],
            polygon=poly,
            name=tags.get("name", ""),
            building_type=tags.get("building", "yes"),
            tags=tags,
        ))
    logger.info(f"Parsed {len(results)} buildings")
    return results


def parse_landuse(
    ways: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[LandUseArea]:
    """Parse land use ways (parks, water, zones) into LandUseArea objects."""
    # Map OSM tags to canonical landuse types
    results = []
    for way in ways:
        tags = way.get("tags", {})
        landuse_type = None

        if tags.get("leisure") == "park":
            landuse_type = "park"
        elif tags.get("natural") == "water":
            landuse_type = "water"
        elif tags.get("waterway") == "riverbank":
            landuse_type = "water"
        elif tags.get("landuse") in ("industrial", "commercial", "residential"):
            landuse_type = tags["landuse"]
        else:
            continue

        poly = _make_polygon(way["nodes"], proj)
        if poly is None:
            continue
        if boundary and not boundary.intersects(poly):
            continue
        if boundary:
            clipped = poly.intersection(boundary)
            if clipped.is_empty or not isinstance(clipped, Polygon):
                continue
            poly = clipped
        results.append(LandUseArea(
            way_id=way["id"],
            polygon=poly,
            name=tags.get("name", ""),
            landuse_type=landuse_type,
            tags=tags,
        ))
    logger.info(f"Parsed {len(results)} land use areas")
    return results


def parse_railways(
    ways: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[RailwayLine]:
    """Parse ways with railway=* tag into RailwayLine objects."""
    valid_types = {"rail", "tram", "light_rail", "subway"}
    results = []
    for way in ways:
        tags = way.get("tags", {})
        rtype = tags.get("railway", "")
        if rtype not in valid_types:
            continue
        line = _make_linestring(way["nodes"], proj)
        if line is None:
            continue
        if boundary:
            clipped = line.intersection(boundary)
            if clipped.is_empty:
                continue
            if isinstance(clipped, LineString):
                line = clipped
            else:
                # MultiLineString — take the longest part
                parts = [g for g in clipped.geoms if isinstance(g, LineString) and not g.is_empty]
                if not parts:
                    continue
                line = max(parts, key=lambda g: g.length)
        results.append(RailwayLine(
            way_id=way["id"],
            centerline=line,
            name=tags.get("name", ""),
            railway_type=rtype,
            tags=tags,
        ))
    logger.info(f"Parsed {len(results)} railways")
    return results


def parse_parking(
    ways: list[dict],
    nodes: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[ParkingArea]:
    """Parse parking lots (ways) and parking spaces (nodes)."""
    results = []

    # Parking lot polygons from ways
    for way in ways:
        tags = way.get("tags", {})
        if tags.get("amenity") != "parking":
            continue
        poly = _make_polygon(way["nodes"], proj)
        if poly is None:
            continue
        if boundary and not boundary.intersects(poly):
            continue
        if boundary:
            clipped = poly.intersection(boundary)
            if clipped.is_empty or not isinstance(clipped, Polygon):
                continue
            poly = clipped
        results.append(ParkingArea(
            element_id=way["id"],
            polygon=poly,
            parking_type=tags.get("parking", "surface"),
            name=tags.get("name", ""),
            capacity=_parse_int(tags.get("capacity")),
            tags=tags,
        ))

    # Parking space points from nodes
    for node in nodes:
        tags = node.get("tags", {})
        if tags.get("amenity") != "parking_space":
            continue
        pt = _make_point(node, proj)
        if boundary and not boundary.contains(pt):
            continue
        results.append(ParkingArea(
            element_id=node["id"],
            point=pt,
            parking_type="street",
            name=tags.get("name", ""),
            capacity=_parse_int(tags.get("capacity")),
            tags=tags,
        ))

    logger.info(f"Parsed {len(results)} parking features")
    return results


def parse_point_features(
    nodes: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[PointFeature]:
    """Parse tagged nodes into PointFeature objects.

    Detects: traffic_signal, tree, bench, street_lamp, manhole.
    """
    # Tag → feature_type mapping
    type_map = [
        (("highway", "traffic_signals"), "traffic_signal"),
        (("natural", "tree"), "tree"),
        (("amenity", "bench"), "bench"),
        (("highway", "street_lamp"), "street_lamp"),
        (("man_made", "manhole"), "manhole"),
    ]

    results = []
    for node in nodes:
        tags = node.get("tags", {})
        feature_type = None
        for (tag_key, tag_val), ftype in type_map:
            if tags.get(tag_key) == tag_val:
                feature_type = ftype
                break
        if feature_type is None:
            continue
        pt = _make_point(node, proj)
        if boundary and not boundary.contains(pt):
            continue
        results.append(PointFeature(
            node_id=node["id"],
            point=pt,
            feature_type=feature_type,
            tags=tags,
        ))
    logger.info(f"Parsed {len(results)} point features")
    return results


def parse_cycleways(
    ways: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[CyclewayLine]:
    """Parse ways with highway=cycleway or cycleway=* tag."""
    results = []
    for way in ways:
        tags = way.get("tags", {})
        is_cycleway = tags.get("highway") == "cycleway" or "cycleway" in tags
        if not is_cycleway:
            continue
        # Skip roads that have a cycleway tag — they're already in road layers
        if tags.get("highway") not in (None, "cycleway"):
            continue
        line = _make_linestring(way["nodes"], proj)
        if line is None:
            continue
        if boundary:
            clipped = line.intersection(boundary)
            if clipped.is_empty:
                continue
            if isinstance(clipped, LineString):
                line = clipped
            else:
                parts = [g for g in clipped.geoms if isinstance(g, LineString) and not g.is_empty]
                if not parts:
                    continue
                line = max(parts, key=lambda g: g.length)

        ctype = tags.get("cycleway", "lane")
        if tags.get("highway") == "cycleway":
            ctype = "path"

        results.append(CyclewayLine(
            way_id=way["id"],
            centerline=line,
            name=tags.get("name", ""),
            cycleway_type=ctype,
            tags=tags,
        ))
    logger.info(f"Parsed {len(results)} cycleways")
    return results


def parse_utilities(
    ways: list[dict],
    nodes: list[dict],
    proj: ProjectionHelper,
    boundary: Polygon | None = None,
) -> list[UtilityFeature]:
    """Parse power lines (ways) and manholes (nodes)."""
    results = []

    # Power lines from ways
    for way in ways:
        tags = way.get("tags", {})
        power = tags.get("power", "")
        if power not in ("line", "minor_line"):
            continue
        line = _make_linestring(way["nodes"], proj)
        if line is None:
            continue
        if boundary:
            clipped = line.intersection(boundary)
            if clipped.is_empty:
                continue
            if isinstance(clipped, LineString):
                line = clipped
            else:
                parts = [g for g in clipped.geoms if isinstance(g, LineString) and not g.is_empty]
                if not parts:
                    continue
                line = max(parts, key=lambda g: g.length)
        utype = "power_line" if power == "line" else "minor_power_line"
        results.append(UtilityFeature(
            element_id=way["id"],
            geometry=line,
            utility_type=utype,
            tags=tags,
        ))

    # Manholes from nodes
    for node in nodes:
        tags = node.get("tags", {})
        if tags.get("man_made") != "manhole":
            continue
        pt = _make_point(node, proj)
        if boundary and not boundary.contains(pt):
            continue
        results.append(UtilityFeature(
            element_id=node["id"],
            geometry=pt,
            utility_type="manhole",
            tags=tags,
        ))

    logger.info(f"Parsed {len(results)} utility features")
    return results


def _parse_int(val) -> int | None:
    """Try to parse an integer, return None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
