"""Generate lane marking polylines from road centerlines."""

import logging
from shapely.geometry import LineString
from app.services.geometry.models import RoadSegment
from app.services.geometry.road_edges import _safe_offset

logger = logging.getLogger(__name__)

LaneMarking = tuple[LineString, str]  # (geometry, "solid" | "dashed")


def generate_lane_markings(
    segment: RoadSegment,
) -> list[LaneMarking]:
    """Generate interior lane divider lines for a road segment.

    For N lanes, generates N-1 dividers.
    Two-way roads: center divider is solid, others dashed.
    One-way roads: all dividers are dashed.

    Returns list of (LineString, linetype) tuples.
    """
    lanes = segment.lanes
    if lanes < 2:
        return []

    centerline = segment.centerline
    half_width = segment.width_m / 2.0
    lane_width = segment.lane_width_m
    oneway = segment.oneway

    markings: list[LaneMarking] = []

    # Offsets from centerline for each lane boundary
    # Lane boundaries at: -width/2 + lane_width * i for i in range(1, lanes)
    for i in range(1, lanes):
        offset = -half_width + lane_width * i

        line = _safe_offset(centerline, offset, f"{segment.name} lane-{i}")
        if line is None:
            continue

        # Determine linetype
        if oneway:
            linetype = "dashed"
        else:
            # Center divider index for two-way roads
            center_idx = lanes // 2
            if i == center_idx:
                linetype = "solid"
            else:
                linetype = "dashed"

        markings.append((line, linetype))

    return markings


def generate_carriageway_lane_markings(
    centerline: LineString,
    carriageway_width: float,
    lane_count: int,
    lane_width: float,
    name: str = "",
) -> list[LaneMarking]:
    """Generate lane markings for a single carriageway of a divided road.

    All markings are dashed (same direction of travel within a carriageway).
    """
    if lane_count < 2:
        return []

    half_cw = carriageway_width / 2.0
    markings: list[LaneMarking] = []

    for i in range(1, lane_count):
        offset = -half_cw + lane_width * i
        line = _safe_offset(centerline, offset, f"{name} cw-lane-{i}")
        if line is None:
            continue
        markings.append((line, "dashed"))

    return markings
