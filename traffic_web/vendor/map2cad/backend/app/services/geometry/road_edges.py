"""Generate road edge polylines from centerlines using offset_curve."""

import logging
from shapely.geometry import LineString
from shapely import offset_curve
from app.services.geometry.models import RoadSegment

logger = logging.getLogger(__name__)

# Road types that don't get curbs
NO_CURB_TYPES = {"motorway", "trunk", "track"}


def generate_road_edges(
    segment: RoadSegment,
) -> tuple[LineString | None, LineString | None]:
    """Generate left and right road edge polylines for a single road segment.

    Left edge = positive offset (left side of travel direction).
    Right edge = negative offset (right side of travel direction).

    Returns (left_edge, right_edge) — either may be None on failure.
    """
    half_width = segment.width_m / 2.0
    centerline = segment.centerline

    left_edge = _safe_offset(centerline, half_width, segment.name)
    right_edge = _safe_offset(centerline, -half_width, segment.name)

    return left_edge, right_edge


def generate_divided_road_edges(
    segment: RoadSegment,
) -> dict:
    """Generate edges for a divided road with a median.

    Returns dict with keys:
        left_carriageway_edges: (left_edge, right_edge)
        right_carriageway_edges: (left_edge, right_edge)
        median_lines: (left_median_edge, right_median_edge)
        left_carriageway_width: float
        right_carriageway_width: float
        left_carriageway_lanes: int
        right_carriageway_lanes: int
    """
    median_w = segment.median_width_m
    carriageway_width = (segment.width_m - median_w) / 2.0
    half_median = median_w / 2.0
    centerline = segment.centerline

    # Offset centerlines for each carriageway
    left_cl = _safe_offset(centerline, half_median, f"{segment.name} left-CL")
    right_cl = _safe_offset(centerline, -half_median, f"{segment.name} right-CL")

    left_edges = (None, None)
    right_edges = (None, None)
    median_lines = (None, None)

    half_cw = carriageway_width / 2.0

    if left_cl:
        left_outer = _safe_offset(left_cl, half_cw, f"{segment.name} left-outer")
        left_inner = _safe_offset(left_cl, -half_cw, f"{segment.name} left-inner")
        left_edges = (left_outer, left_inner)
        median_lines = (left_inner, None)

    if right_cl:
        right_inner = _safe_offset(right_cl, half_cw, f"{segment.name} right-inner")
        right_outer = _safe_offset(right_cl, -half_cw, f"{segment.name} right-outer")
        right_edges = (right_inner, right_outer)
        median_lines = (median_lines[0], right_inner)

    total_lanes = segment.lanes
    left_lanes = (total_lanes + 1) // 2
    right_lanes = total_lanes // 2

    return {
        "left_carriageway_edges": left_edges,
        "right_carriageway_edges": right_edges,
        "median_lines": median_lines,
        "left_carriageway_width": carriageway_width,
        "right_carriageway_width": carriageway_width,
        "left_carriageway_lanes": left_lanes,
        "right_carriageway_lanes": right_lanes,
        "left_centerline": left_cl,
        "right_centerline": right_cl,
    }


def _safe_offset(
    line: LineString, distance: float, label: str = ""
) -> LineString | None:
    """Offset a LineString with fallback on failure.

    Strategy:
    1. Try offset_curve directly with mitre join and quad_segs=8
    2. On failure, simplify input by 0.1m and retry
    3. On second failure, fall back to buffer exterior
    """
    try:
        result = offset_curve(line, distance, join_style="mitre", quad_segs=8)
        if _is_valid_line(result):
            return result
    except Exception:
        pass

    # Retry with simplified geometry
    try:
        simplified = line.simplify(0.1, preserve_topology=True)
        result = offset_curve(simplified, distance, join_style="mitre", quad_segs=8)
        if _is_valid_line(result):
            logger.debug(f"Used simplified geometry for offset: {label}")
            return result
    except Exception:
        pass

    # Buffer fallback
    try:
        buf = line.buffer(abs(distance), quad_segs=8)
        exterior = buf.exterior
        if distance >= 0:
            # Left side — take the half that's on the left
            result = _extract_side_from_buffer(line, exterior, distance)
        else:
            result = _extract_side_from_buffer(line, exterior, distance)
        if result and _is_valid_line(result):
            logger.debug(f"Used buffer fallback for offset: {label}")
            return result
    except Exception:
        pass

    logger.warning(f"All offset methods failed for: {label}")
    return None


def _extract_side_from_buffer(
    centerline: LineString, exterior: LineString, distance: float
) -> LineString | None:
    """Extract one side of a buffer exterior as a LineString approximation.

    For positive distance (left), take points that are on the left side.
    For negative distance (right), take points on the right side.
    """
    # Simple approach: offset the start/end and interpolate along the buffer
    # For a straight-ish line, we can use the parallel_offset approach
    # Just return the exterior as a rough approximation — better than nothing
    coords = list(exterior.coords)
    if len(coords) < 3:
        return None

    # Split exterior roughly in half based on distance from start/end
    mid_idx = len(coords) // 2
    if distance >= 0:
        side_coords = coords[:mid_idx + 1]
    else:
        side_coords = coords[mid_idx:]

    if len(side_coords) >= 2:
        return LineString(side_coords)
    return None


def _is_valid_line(geom) -> bool:
    """Check if geometry is a valid, non-empty LineString."""
    return (
        isinstance(geom, LineString)
        and not geom.is_empty
        and geom.is_valid
        and len(geom.coords) >= 2
    )
