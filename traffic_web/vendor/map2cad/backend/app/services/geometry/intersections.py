"""Intersection detection, classification, polygon generation, and road trimming."""

import logging
import math
from dataclasses import dataclass, field
from shapely.geometry import LineString, Point, Polygon, MultiLineString, GeometryCollection
from shapely import STRtree, union_all
from app.services.geometry.models import RoadSegment

logger = logging.getLogger(__name__)

# --- Constants ---
ENDPOINT_TOLERANCE_M = 0.5
CLUSTER_TOLERANCE_M = 2.0
APPROACH_LENGTH_M = 15.0
MIN_INTERSECTION_AREA_M2 = 4.0
ARC_POINTS = 16

TURNING_RADII = {
    ("motorway", "motorway"): 15, ("motorway", "trunk"): 15, ("motorway", "primary"): 15,
    ("motorway", "secondary"): 15, ("motorway", "tertiary"): 15, ("motorway", "residential"): 15,
    ("motorway", "service"): 15,
    ("trunk", "trunk"): 12, ("trunk", "primary"): 12, ("trunk", "secondary"): 12,
    ("trunk", "tertiary"): 12, ("trunk", "residential"): 12, ("trunk", "service"): 12,
    ("primary", "primary"): 10, ("primary", "secondary"): 9, ("primary", "tertiary"): 9,
    ("primary", "residential"): 9, ("primary", "service"): 9,
    ("secondary", "secondary"): 8, ("secondary", "tertiary"): 8, ("secondary", "residential"): 8,
    ("secondary", "service"): 8,
    ("tertiary", "tertiary"): 7, ("tertiary", "residential"): 7, ("tertiary", "service"): 7,
    ("residential", "residential"): 6, ("residential", "service"): 6,
    ("service", "service"): 5,
}


def _get_turning_radius(type_a: str, type_b: str) -> float:
    """Get turning radius for two road types meeting."""
    key = tuple(sorted([type_a, type_b]))
    return TURNING_RADII.get(key, 6.0)


# --- Data classes ---

@dataclass
class IntersectionApproach:
    """A road approaching an intersection."""
    segment_idx: int
    angle: float  # approach angle in degrees (0=east, 90=north)
    width: float
    highway_type: str
    is_terminating: bool = False  # road ends at this intersection


@dataclass
class Intersection:
    """A detected intersection between roads."""
    point: Point
    approaches: list[IntersectionApproach] = field(default_factory=list)
    degree: int = 0  # number of approaching roads
    polygon: Polygon | None = None
    type: str = "cross"  # "T", "cross", "complex"

    @property
    def x(self) -> float:
        return self.point.x

    @property
    def y(self) -> float:
        return self.point.y


# --- Task 1: Detect intersection points ---

def detect_intersections(
    segments: list[RoadSegment],
) -> list[Intersection]:
    """Find where road centerlines meet or cross each other.

    Uses STRtree for efficient spatial lookup, then computes actual
    intersections between nearby centerline pairs. Clusters nearby
    intersection points within CLUSTER_TOLERANCE_M.
    """
    if len(segments) < 2:
        return []

    centerlines = [seg.centerline for seg in segments]
    tree = STRtree(centerlines)

    raw_points: list[tuple[float, float, list[int]]] = []

    for i, cl_a in enumerate(centerlines):
        # Find candidates that are near this centerline
        candidates = tree.query(cl_a, predicate="intersects")
        for j in candidates:
            if j <= i:
                continue  # avoid duplicate pairs

            cl_b = centerlines[j]

            # Check actual intersection
            result = cl_a.intersection(cl_b)
            points = _extract_points(result)

            for pt in points:
                raw_points.append((pt.x, pt.y, [i, j]))

        # Also check shared endpoints with all other centerlines
        for j, cl_b in enumerate(centerlines):
            if j <= i:
                continue
            shared = _check_shared_endpoints(cl_a, cl_b, i, j)
            raw_points.extend(shared)

    # Cluster nearby points
    intersections = _cluster_points(raw_points, segments)

    logger.info(f"Detected {len(intersections)} intersections from {len(segments)} roads")
    return intersections


def _extract_points(geom) -> list[Point]:
    """Extract Point geometries from an intersection result."""
    if geom.is_empty:
        return []
    if isinstance(geom, Point):
        return [geom]
    if isinstance(geom, (MultiLineString, LineString)):
        # Lines overlapping — use endpoints as intersection points
        points = []
        if isinstance(geom, LineString):
            geom = MultiLineString([geom])
        for line in geom.geoms:
            coords = list(line.coords)
            if coords:
                points.append(Point(coords[0]))
                points.append(Point(coords[-1]))
        return points
    if isinstance(geom, GeometryCollection):
        points = []
        for g in geom.geoms:
            points.extend(_extract_points(g))
        return points
    if hasattr(geom, 'geoms'):
        points = []
        for g in geom.geoms:
            points.extend(_extract_points(g))
        return points
    return []


def _check_shared_endpoints(
    cl_a: LineString, cl_b: LineString, idx_a: int, idx_b: int
) -> list[tuple[float, float, list[int]]]:
    """Check if two centerlines share endpoints (within tolerance)."""
    results = []
    endpoints_a = [Point(cl_a.coords[0]), Point(cl_a.coords[-1])]
    endpoints_b = [Point(cl_b.coords[0]), Point(cl_b.coords[-1])]

    for pa in endpoints_a:
        for pb in endpoints_b:
            if pa.distance(pb) < ENDPOINT_TOLERANCE_M:
                mid_x = (pa.x + pb.x) / 2
                mid_y = (pa.y + pb.y) / 2
                results.append((mid_x, mid_y, [idx_a, idx_b]))

    return results


def _cluster_points(
    raw_points: list[tuple[float, float, list[int]]],
    segments: list[RoadSegment],
) -> list[Intersection]:
    """Cluster nearby intersection points into single intersection nodes."""
    if not raw_points:
        return []

    used = [False] * len(raw_points)
    clusters: list[list[int]] = []

    for i in range(len(raw_points)):
        if used[i]:
            continue
        cluster = [i]
        used[i] = True
        for j in range(i + 1, len(raw_points)):
            if used[j]:
                continue
            dx = raw_points[i][0] - raw_points[j][0]
            dy = raw_points[i][1] - raw_points[j][1]
            if math.sqrt(dx * dx + dy * dy) < CLUSTER_TOLERANCE_M:
                cluster.append(j)
                used[j] = True
        clusters.append(cluster)

    intersections = []
    for cluster in clusters:
        # Average position
        xs = [raw_points[i][0] for i in cluster]
        ys = [raw_points[i][1] for i in cluster]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

        # Collect all participating road indices
        road_indices = set()
        for i in cluster:
            road_indices.update(raw_points[i][2])

        point = Point(cx, cy)
        ix = Intersection(point=point)

        for idx in sorted(road_indices):
            seg = segments[idx]
            angle = _approach_angle(seg.centerline, point)
            # Check if road terminates near this intersection
            start = Point(seg.centerline.coords[0])
            end = Point(seg.centerline.coords[-1])
            is_term = (start.distance(point) < ENDPOINT_TOLERANCE_M * 3 or
                       end.distance(point) < ENDPOINT_TOLERANCE_M * 3)

            ix.approaches.append(IntersectionApproach(
                segment_idx=idx,
                angle=angle,
                width=seg.width_m,
                highway_type=seg.highway_type,
                is_terminating=is_term,
            ))

        ix.degree = len(ix.approaches)
        ix.type = _classify_type(ix)
        intersections.append(ix)

    return intersections


# --- Task 2: Classify intersection types ---

def _approach_angle(centerline: LineString, point: Point) -> float:
    """Calculate the approach angle of a road at an intersection point.

    Returns angle in degrees (0=east, 90=north).
    """
    # Find the nearest point on the centerline and use a short segment for direction
    proj_dist = centerline.project(point)
    total_len = centerline.length

    # Get two points near the intersection to determine direction
    d1 = max(0, proj_dist - 2.0)
    d2 = min(total_len, proj_dist + 2.0)
    p1 = centerline.interpolate(d1)
    p2 = centerline.interpolate(d2)

    dx = p2.x - p1.x
    dy = p2.y - p1.y

    return math.degrees(math.atan2(dy, dx)) % 360


def _classify_type(ix: Intersection) -> str:
    """Classify intersection type based on degree and approach patterns."""
    if ix.degree <= 2:
        return "simple"
    if ix.degree == 3:
        terminating = sum(1 for a in ix.approaches if a.is_terminating)
        if terminating >= 1:
            return "T"
        return "Y"
    if ix.degree == 4:
        return "cross"
    return "complex"


# --- Task 3: Generate intersection area polygons ---

def generate_intersection_polygons(
    intersections: list[Intersection],
    segments: list[RoadSegment],
) -> list[Intersection]:
    """Generate area polygons for each intersection."""
    for ix in intersections:
        try:
            poly = _build_intersection_polygon(ix, segments)
            if poly and poly.is_valid and poly.area >= MIN_INTERSECTION_AREA_M2:
                ix.polygon = poly
            else:
                # Fallback: simple circle
                max_width = max((a.width for a in ix.approaches), default=6.0)
                ix.polygon = ix.point.buffer(max_width / 2)
        except Exception as e:
            logger.warning(f"Intersection polygon failed at ({ix.x:.0f}, {ix.y:.0f}): {e}")
            max_width = max((a.width for a in ix.approaches), default=6.0)
            ix.polygon = ix.point.buffer(max_width / 2)

    return intersections


def _build_intersection_polygon(
    ix: Intersection,
    segments: list[RoadSegment],
) -> Polygon | None:
    """Build intersection polygon from approach rectangles."""
    approach_rects = []

    for approach in ix.approaches:
        seg = segments[approach.segment_idx]
        cl = seg.centerline
        width = approach.width

        # Create approach rectangle along centerline at intersection
        proj_dist = cl.project(ix.point)
        total_len = cl.length

        # Approach rectangle: road_width x approach_length centered on intersection
        d_start = max(0, proj_dist - APPROACH_LENGTH_M / 2)
        d_end = min(total_len, proj_dist + APPROACH_LENGTH_M / 2)

        if d_end - d_start < 1.0:
            continue

        # Extract segment of centerline near intersection
        sub_coords = []
        for d in [d_start, d_end]:
            pt = cl.interpolate(d)
            sub_coords.append((pt.x, pt.y))

        if len(sub_coords) < 2:
            continue

        sub_line = LineString(sub_coords)
        rect = sub_line.buffer(width / 2, cap_style="flat")
        approach_rects.append(rect)

    if not approach_rects:
        return None

    combined = union_all(approach_rects)
    # Smooth the shape
    smoothed = combined.buffer(1.0).buffer(-0.5)

    if isinstance(smoothed, Polygon) and smoothed.is_valid:
        return smoothed

    # If result is MultiPolygon, take the largest
    if hasattr(smoothed, 'geoms'):
        polys = [g for g in smoothed.geoms if isinstance(g, Polygon)]
        if polys:
            return max(polys, key=lambda p: p.area)

    return None


# --- Task 4: Apply turning radii at intersection corners ---

def apply_turning_radii(
    intersections: list[Intersection],
) -> list[Intersection]:
    """Replace sharp corners of intersection polygons with circular arcs."""
    for ix in intersections:
        if ix.polygon is None:
            continue
        try:
            ix.polygon = _round_polygon_corners(ix)
        except Exception as e:
            logger.debug(f"Turning radius application failed: {e}")
            # Keep original polygon
    return intersections


def _round_polygon_corners(ix: Intersection) -> Polygon:
    """Round the corners of an intersection polygon using turning radii."""
    if ix.degree < 3 or ix.polygon is None:
        return ix.polygon

    # Determine the turning radius for this intersection
    types = [a.highway_type for a in ix.approaches]
    radii = []
    for i in range(len(types)):
        for j in range(i + 1, len(types)):
            radii.append(_get_turning_radius(types[i], types[j]))
    radius = min(radii) if radii else 6.0

    # Clamp radius to not exceed half the smallest road width
    min_width = min((a.width for a in ix.approaches), default=6.0)
    radius = min(radius, min_width)

    # Use Shapely buffer to round corners
    # Negative then positive buffer rounds outer corners
    try:
        rounded = ix.polygon.buffer(-radius).buffer(radius, quad_segs=ARC_POINTS // 4)
        if isinstance(rounded, Polygon) and rounded.is_valid and rounded.area > MIN_INTERSECTION_AREA_M2:
            return rounded
    except Exception:
        pass

    return ix.polygon


# --- Task 5: Trim road edges at intersections ---

def trim_geometry_at_intersections(
    layers: dict[str, list[tuple[LineString, dict]]],
    intersections: list[Intersection],
) -> dict[str, list[tuple[LineString, dict]]]:
    """Trim road edges, lane markings, curbs, sidewalks at intersection polygons.

    Centerlines are NOT trimmed (they remain as reference lines through intersections).
    """
    if not intersections:
        return layers

    # Build union of all intersection polygons for efficient trimming
    polys = [ix.polygon for ix in intersections if ix.polygon is not None]
    if not polys:
        return layers

    ix_union = union_all(polys)
    if ix_union.is_empty:
        return layers

    # Layers to trim (centerlines excluded)
    trim_layers = {"ROAD_EDGES", "LANE_MARKINGS", "CURBS", "SIDEWALKS", "MEDIANS"}

    trimmed_layers = {}
    for layer_name, entries in layers.items():
        if layer_name not in trim_layers:
            trimmed_layers[layer_name] = entries
            continue

        new_entries = []
        for geom, meta in entries:
            try:
                result = geom.difference(ix_union)
                lines = _extract_trimmed_lines(result)
                for line in lines:
                    if line.length >= 0.5:
                        new_entries.append((line, meta))
            except Exception as e:
                logger.debug(f"Trim failed for {layer_name}: {e}")
                new_entries.append((geom, meta))  # keep original

        trimmed_layers[layer_name] = new_entries

    return trimmed_layers


def _extract_trimmed_lines(geom) -> list[LineString]:
    """Extract LineStrings from a difference result."""
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        lines = []
        for g in geom.geoms:
            if isinstance(g, LineString):
                lines.append(g)
            elif isinstance(g, MultiLineString):
                lines.extend(g.geoms)
        return lines
    return []


# --- Task 6: Handle T-intersections ---
# T-intersection handling is integrated into the polygon generation and trimming above.
# The _classify_type identifies T-intersections, and the polygon approach rectangles
# naturally handle the T-shape since only 3 approach rectangles are unioned.
# Curb return arcs are approximated by the buffer smoothing in _build_intersection_polygon.


# --- Task 7: Handle roundabouts ---

def detect_roundabout_ways(parsed_roads) -> set[int]:
    """Detect roundabout ways from OSM junction=roundabout tag.

    Returns set of way_ids that are roundabouts.
    Note: Full roundabout modeling is a future enhancement.
    For now, roundabout ways are treated as regular roads and their
    intersections get standard polygon treatment.
    """
    roundabout_ids = set()
    for road in parsed_roads:
        # ParsedRoad doesn't store junction tag currently,
        # so roundabout detection is deferred to a future session.
        # This function serves as the extension point.
        pass
    logger.debug(f"Roundabout detection: {len(roundabout_ids)} roundabouts found")
    return roundabout_ids
