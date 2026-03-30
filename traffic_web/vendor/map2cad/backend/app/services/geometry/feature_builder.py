"""Convert parsed feature models into DXF-ready geometry organized by layer."""

import logging

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

logger = logging.getLogger(__name__)

# Standard rail gauge half-width (1.435m / 2)
RAIL_HALF_GAUGE = 0.7175

# Landuse type → DXF layer mapping
LANDUSE_LAYER_MAP = {
    "park": "LANDUSE_PARK",
    "water": "LANDUSE_WATER",
    "industrial": "LANDUSE_ZONES",
    "commercial": "LANDUSE_ZONES",
    "residential": "LANDUSE_ZONES",
}


def build_feature_geometry(
    buildings: list[BuildingFootprint] | None = None,
    landuse: list[LandUseArea] | None = None,
    railways: list[RailwayLine] | None = None,
    parking: list[ParkingArea] | None = None,
    points: list[PointFeature] | None = None,
    cycleways: list[CyclewayLine] | None = None,
    utilities: list[UtilityFeature] | None = None,
    options: dict | None = None,
) -> tuple[
    dict[str, list[tuple[LineString, dict]]],
    dict[str, list[tuple[Polygon, dict]]],
    dict[str, list[tuple[Point, dict]]],
    list[str],
]:
    """Build DXF-ready geometry from parsed features.

    Returns:
        (line_layers, polygon_layers, point_layers, warnings)
    """
    line_layers: dict[str, list[tuple[LineString, dict]]] = {}
    polygon_layers: dict[str, list[tuple[Polygon, dict]]] = {}
    point_layers: dict[str, list[tuple[Point, dict]]] = {}
    warnings: list[str] = []

    # --- Buildings ---
    if buildings:
        polys = []
        for b in buildings:
            polys.append((b.polygon, {"name": b.name, "building_type": b.building_type}))
        polygon_layers["BUILDINGS"] = polys
        logger.info(f"Feature geometry: {len(polys)} buildings")

    # --- Land use ---
    if landuse:
        for area in landuse:
            layer = LANDUSE_LAYER_MAP.get(area.landuse_type)
            if not layer:
                continue
            if layer not in polygon_layers:
                polygon_layers[layer] = []
            polygon_layers[layer].append(
                (area.polygon, {"name": area.name, "landuse_type": area.landuse_type})
            )
        total_lu = sum(len(v) for k, v in polygon_layers.items() if k.startswith("LANDUSE"))
        logger.info(f"Feature geometry: {total_lu} land use areas")

    # --- Railways ---
    if railways:
        rail_lines = []
        for r in railways:
            if r.railway_type == "rail":
                # Dual-rail representation: offset centerline by ± half gauge
                try:
                    left = r.centerline.offset_curve(RAIL_HALF_GAUGE)
                    right = r.centerline.offset_curve(-RAIL_HALF_GAUGE)
                    if isinstance(left, LineString) and not left.is_empty:
                        rail_lines.append((left, {"name": r.name, "railway_type": r.railway_type, "side": "left"}))
                    if isinstance(right, LineString) and not right.is_empty:
                        rail_lines.append((right, {"name": r.name, "railway_type": r.railway_type, "side": "right"}))
                except Exception:
                    # Fallback: single centerline
                    rail_lines.append((r.centerline, {"name": r.name, "railway_type": r.railway_type}))
            else:
                # Tram/light_rail/subway: single line
                rail_lines.append((r.centerline, {"name": r.name, "railway_type": r.railway_type}))
        line_layers["RAILWAYS"] = rail_lines
        logger.info(f"Feature geometry: {len(rail_lines)} railway lines")

    # --- Parking ---
    if parking:
        parking_polys = []
        parking_points = []
        for p in parking:
            if p.polygon:
                parking_polys.append(
                    (p.polygon, {"name": p.name, "parking_type": p.parking_type})
                )
            if p.point:
                parking_points.append(
                    (p.point, {"name": p.name, "feature_type": "parking_space"})
                )
        if parking_polys:
            polygon_layers["PARKING"] = parking_polys
        if parking_points:
            point_layers["PARKING"] = parking_points
        logger.info(f"Feature geometry: {len(parking_polys)} parking lots, {len(parking_points)} parking spaces")

    # --- Point features ---
    if points:
        signals = []
        furniture = []
        for pf in points:
            meta = {"feature_type": pf.feature_type}
            if pf.feature_type == "traffic_signal":
                signals.append((pf.point, meta))
            else:
                furniture.append((pf.point, meta))
        if signals:
            point_layers["TRAFFIC_SIGNALS"] = signals
        if furniture:
            point_layers["STREET_FURNITURE"] = furniture
        logger.info(f"Feature geometry: {len(signals)} traffic signals, {len(furniture)} street furniture")

    # --- Cycleways ---
    if cycleways:
        cycle_lines = []
        for c in cycleways:
            cycle_lines.append((c.centerline, {"name": c.name, "cycleway_type": c.cycleway_type}))
        line_layers["CYCLEWAYS"] = cycle_lines
        logger.info(f"Feature geometry: {len(cycle_lines)} cycleways")

    # --- Utilities ---
    if utilities:
        util_lines = []
        util_points = []
        for u in utilities:
            meta = {"utility_type": u.utility_type}
            if isinstance(u.geometry, LineString):
                util_lines.append((u.geometry, meta))
            elif isinstance(u.geometry, Point):
                util_points.append((u.geometry, {"feature_type": "manhole", **meta}))
        if util_lines:
            line_layers["UTILITIES"] = util_lines
        if util_points:
            if "UTILITIES" not in point_layers:
                point_layers["UTILITIES"] = []
            point_layers["UTILITIES"].extend(util_points)
        logger.info(f"Feature geometry: {len(util_lines)} utility lines, {len(util_points)} utility points")

    return line_layers, polygon_layers, point_layers, warnings
