"""Generate DXF CAD files with 19 layers from road and feature geometry data."""

import logging
import math
import os
import time
from datetime import datetime

import ezdxf
from ezdxf import units
from shapely.geometry import LineString, Point, Polygon

logger = logging.getLogger(__name__)

# --- Layer definitions ---

LAYER_DEFS = {
    # Road layers (original 9)
    "ROAD_EDGES":      {"color": 7,   "linetype": "CONTINUOUS", "lineweight": 50},
    "CENTERLINES":     {"color": 1,   "linetype": "DASHDOT",    "lineweight": 18},
    "INTERSECTIONS":   {"color": 30,  "linetype": "CONTINUOUS", "lineweight": 25},
    "ROAD_NAMES":      {"color": 7,   "linetype": "CONTINUOUS", "lineweight": 13},
    "LANE_MARKINGS":   {"color": 2,   "linetype": "DASHED",     "lineweight": 13},
    "SIDEWALKS":       {"color": 9,   "linetype": "CONTINUOUS", "lineweight": 35},
    "CURBS":           {"color": 8,   "linetype": "CONTINUOUS", "lineweight": 25},
    "MEDIANS":         {"color": 3,   "linetype": "CONTINUOUS", "lineweight": 25},
    "BOUNDARY":        {"color": 6,   "linetype": "DASHED",     "lineweight": 18},
    # Feature layers (new 10)
    "BUILDINGS":       {"color": 253, "linetype": "CONTINUOUS", "lineweight": 25},
    "LANDUSE_PARK":    {"color": 82,  "linetype": "CONTINUOUS", "lineweight": 18},
    "LANDUSE_WATER":   {"color": 150, "linetype": "CONTINUOUS", "lineweight": 18},
    "LANDUSE_ZONES":   {"color": 52,  "linetype": "CONTINUOUS", "lineweight": 18},
    "RAILWAYS":        {"color": 16,  "linetype": "DASHDOT",    "lineweight": 35},
    "PARKING":         {"color": 42,  "linetype": "CONTINUOUS", "lineweight": 18},
    "TRAFFIC_SIGNALS": {"color": 10,  "linetype": "CONTINUOUS", "lineweight": 25},
    "STREET_FURNITURE":{"color": 92,  "linetype": "CONTINUOUS", "lineweight": 13},
    "CYCLEWAYS":       {"color": 4,   "linetype": "DASHED",     "lineweight": 25},
    "UTILITIES":       {"color": 200, "linetype": "DASHDOT",    "lineweight": 18},
}

# Point feature radii (meters) for CIRCLE entities
POINT_RADII = {
    "traffic_signal": 1.0,
    "tree": 0.5,
    "bench": 0.3,
    "street_lamp": 0.3,
    "manhole": 0.4,
    "parking_space": 0.5,
    "default": 0.4,
}

# Hatch patterns for polygon layers
HATCH_DEFS = {
    "LANDUSE_PARK":  {"pattern": "ANSI31", "scale": 1.0, "color": 82},
    "LANDUSE_WATER": {"pattern": "ANSI37", "scale": 1.0, "color": 150},
}

# Text height by classification
TEXT_HEIGHT = {
    "main": 2.5,
    "secondary": 2.0,
    "local": 1.5,
}

LABEL_INTERVAL_M = 200.0


# --- Task 1: Create DXF document ---

def create_dxf_document() -> ezdxf.document.Drawing:
    """Create a new DXF R2018 document with proper CAD settings."""
    doc = ezdxf.new("R2018")

    # Units: meters
    doc.header["$INSUNITS"] = units.M
    doc.header["$LTSCALE"] = 1.0

    # Register custom linetypes
    doc.linetypes.add("DASHED", pattern=[0.5, 0.25, -0.25])
    doc.linetypes.add("DASHDOT", pattern=[1.0, 0.5, -0.25, 0.0, -0.25])

    return doc


# --- Task 2: Create layers ---

def create_layers(doc: ezdxf.document.Drawing) -> None:
    """Create all CAD layers with proper colors, linetypes, and lineweights."""
    for name, props in LAYER_DEFS.items():
        layer = doc.layers.add(
            name,
            color=props["color"],
            linetype=props["linetype"],
        )
        layer.dxf.lineweight = props["lineweight"]


# --- Task 3 & 4: Write line geometry ---

def write_line_layers(
    doc: ezdxf.document.Drawing,
    layers: dict[str, list[tuple[LineString, dict]]],
) -> dict[str, int]:
    """Write all line geometry to their respective DXF layers.

    Returns dict of entity counts per layer.
    """
    msp = doc.modelspace()
    counts = {}

    for layer_name, entries in layers.items():
        if layer_name not in LAYER_DEFS:
            continue

        count = 0
        for geom, meta in entries:
            if not isinstance(geom, LineString) or geom.is_empty:
                continue

            coords = list(geom.coords)
            if len(coords) < 2:
                continue

            attribs = {"layer": layer_name}

            # Per-entity linetype override for lane markings
            if layer_name == "LANE_MARKINGS":
                linetype = meta.get("linetype", "DASHED")
                if linetype == "solid":
                    attribs["linetype"] = "CONTINUOUS"
                else:
                    attribs["linetype"] = "DASHED"

            msp.add_lwpolyline(coords, dxfattribs=attribs)
            count += 1

        counts[layer_name] = count

    return counts


# --- Task 5: Write intersection polygons ---

def write_intersections(
    doc: ezdxf.document.Drawing,
    intersections: list,
) -> int:
    """Write intersection polygons as closed polylines on INTERSECTIONS layer.

    Returns entity count.
    """
    msp = doc.modelspace()
    count = 0

    for ix in intersections:
        poly = getattr(ix, "polygon", None)
        if poly is None or not isinstance(poly, Polygon) or poly.is_empty:
            continue

        coords = list(poly.exterior.coords)
        if len(coords) < 3:
            continue

        # Closed polyline
        msp.add_lwpolyline(
            coords,
            close=True,
            dxfattribs={"layer": "INTERSECTIONS"},
        )
        count += 1

        # Add hatch fill
        try:
            hatch = msp.add_hatch(
                color=30,
                dxfattribs={"layer": "INTERSECTIONS"},
            )
            hatch.set_pattern_fill("ANSI31", scale=0.5)
            hatch.paths.add_polyline_path(coords, is_closed=True)
            count += 1
        except Exception as e:
            logger.debug(f"Hatch creation failed: {e}")

    return count


# --- Write polygon layers (buildings, land use, parking) ---

def write_polygon_layers(
    doc: ezdxf.document.Drawing,
    polygon_layers: dict[str, list[tuple[Polygon, dict]]],
) -> dict[str, int]:
    """Write polygon features as closed polylines, with optional hatch fill.

    Returns dict of entity counts per layer.
    """
    msp = doc.modelspace()
    counts = {}

    for layer_name, entries in polygon_layers.items():
        if layer_name not in LAYER_DEFS:
            continue

        count = 0
        for geom, meta in entries:
            if not isinstance(geom, Polygon) or geom.is_empty:
                continue

            coords = list(geom.exterior.coords)
            if len(coords) < 3:
                continue

            # Closed polyline outline
            msp.add_lwpolyline(
                coords,
                close=True,
                dxfattribs={"layer": layer_name},
            )
            count += 1

            # Optional hatch fill for specific layers
            hatch_def = HATCH_DEFS.get(layer_name)
            if hatch_def:
                try:
                    hatch = msp.add_hatch(
                        color=hatch_def["color"],
                        dxfattribs={"layer": layer_name},
                    )
                    hatch.set_pattern_fill(
                        hatch_def["pattern"],
                        scale=hatch_def["scale"],
                    )
                    hatch.paths.add_polyline_path(coords, is_closed=True)
                    count += 1
                except Exception as e:
                    logger.debug(f"Hatch creation failed for {layer_name}: {e}")

        counts[layer_name] = count

    return counts


# --- Write point layers (traffic signals, trees, manholes, etc.) ---

def write_point_layers(
    doc: ezdxf.document.Drawing,
    point_layers: dict[str, list[tuple[Point, dict]]],
) -> dict[str, int]:
    """Write point features as circles on their respective layers.

    Returns dict of entity counts per layer.
    """
    msp = doc.modelspace()
    counts = {}

    for layer_name, entries in point_layers.items():
        if layer_name not in LAYER_DEFS:
            continue

        count = 0
        for geom, meta in entries:
            if not isinstance(geom, Point) or geom.is_empty:
                continue

            feature_type = meta.get("feature_type", "default")
            radius = POINT_RADII.get(feature_type, POINT_RADII["default"])

            msp.add_circle(
                center=(geom.x, geom.y),
                radius=radius,
                dxfattribs={"layer": layer_name},
            )
            count += 1

        counts[layer_name] = count

    return counts


# --- Task 6: Write road name labels ---

def write_road_names(
    doc: ezdxf.document.Drawing,
    layers: dict[str, list[tuple[LineString, dict]]],
) -> int:
    """Place text labels along named road centerlines.

    Returns entity count.
    """
    msp = doc.modelspace()
    count = 0

    centerlines = layers.get("CENTERLINES", [])

    for geom, meta in centerlines:
        name = meta.get("name", "")
        if not name or not isinstance(geom, LineString) or geom.is_empty:
            continue

        highway_type = meta.get("highway_type", "residential")
        classification = _classify_for_text(highway_type)
        height = TEXT_HEIGHT.get(classification, 1.5)

        total_len = geom.length
        if total_len < 5.0:
            continue

        # Place labels at intervals
        positions = []
        if total_len <= LABEL_INTERVAL_M:
            positions.append(total_len / 2)
        else:
            d = LABEL_INTERVAL_M / 2
            while d < total_len:
                positions.append(d)
                d += LABEL_INTERVAL_M

        for d in positions:
            pt = geom.interpolate(d)
            angle = _road_angle_at(geom, d)

            msp.add_text(
                name,
                height=height,
                dxfattribs={
                    "layer": "ROAD_NAMES",
                    "rotation": angle,
                    "halign": 1,  # center
                    "valign": 1,  # middle
                    "insert": (pt.x, pt.y),
                },
            )
            count += 1

    return count


def _road_angle_at(line: LineString, distance: float) -> float:
    """Calculate road angle in degrees at a given distance along the line."""
    total = line.length
    d1 = max(0, distance - 1.0)
    d2 = min(total, distance + 1.0)
    p1 = line.interpolate(d1)
    p2 = line.interpolate(d2)
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    angle = math.degrees(math.atan2(dy, dx))
    # Keep text readable (not upside down)
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    return angle


def _classify_for_text(highway_type: str) -> str:
    """Map highway type to text classification."""
    if highway_type in ("motorway", "trunk", "primary"):
        return "main"
    if highway_type in ("secondary", "tertiary"):
        return "secondary"
    return "local"


# --- Task 7: Write selection boundary ---

def write_boundary(
    doc: ezdxf.document.Drawing,
    boundary: Polygon | None,
) -> int:
    """Write selection boundary polygon to BOUNDARY layer.

    Returns entity count.
    """
    if boundary is None or boundary.is_empty:
        return 0

    msp = doc.modelspace()
    coords = list(boundary.exterior.coords)

    msp.add_lwpolyline(
        coords,
        close=True,
        dxfattribs={
            "layer": "BOUNDARY",
            "linetype": "DASHED",
        },
    )
    return 1


# --- Task 8: Full DXF generation service ---

def generate_dxf(
    layers: dict[str, list[tuple[LineString, dict]]],
    polygon_layers: dict[str, list[tuple[Polygon, dict]]] | None = None,
    point_layers: dict[str, list[tuple[Point, dict]]] | None = None,
    intersections: list | None = None,
    boundary: Polygon | None = None,
    output_dir: str | None = None,
) -> str:
    """Generate a complete DXF file from road and feature geometry data.

    Args:
        layers: Line geometry grouped by layer name {layer: [(geom, meta), ...]}
        polygon_layers: Polygon geometry {layer: [(Polygon, meta), ...]}
        point_layers: Point geometry {layer: [(Point, meta), ...]}
        intersections: List of Intersection objects with polygons
        boundary: Selection boundary polygon (UTM)
        output_dir: Directory for output file. Defaults to temp dir.

    Returns:
        Path to the generated DXF file.
    """
    start = time.time()

    # Create document
    doc = create_dxf_document()
    create_layers(doc)

    # Write all geometry
    line_counts = write_line_layers(doc, layers)
    poly_counts = write_polygon_layers(doc, polygon_layers or {})
    point_counts = write_point_layers(doc, point_layers or {})
    ix_count = write_intersections(doc, intersections or [])
    name_count = write_road_names(doc, layers)
    boundary_count = write_boundary(doc, boundary)

    # Output path
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tmp")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"map_export_{timestamp}.dxf"
    filepath = os.path.join(output_dir, filename)

    try:
        doc.saveas(filepath)
    except OSError as e:
        from app.errors import ExportError
        logger.error(f"Failed to write DXF file: {e}")
        raise ExportError(f"Failed to write DXF file: {e}", code="EXPORT_FAILED")

    elapsed = time.time() - start
    total_entities = (
        sum(line_counts.values())
        + sum(poly_counts.values())
        + sum(point_counts.values())
        + ix_count + name_count + boundary_count
    )
    file_size = os.path.getsize(filepath)

    logger.info(
        f"DXF generated: {filepath} ({file_size / 1024:.1f} KB, "
        f"{total_entities} entities, {elapsed:.2f}s). "
        f"Lines: {', '.join(f'{k}={v}' for k, v in line_counts.items())}, "
        f"Polygons: {', '.join(f'{k}={v}' for k, v in poly_counts.items())}, "
        f"Points: {', '.join(f'{k}={v}' for k, v in point_counts.items())}, "
        f"intersections={ix_count}, names={name_count}, boundary={boundary_count}"
    )

    return filepath
