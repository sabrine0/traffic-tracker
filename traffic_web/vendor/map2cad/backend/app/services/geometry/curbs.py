"""Generate curb lines by offsetting road edges outward."""

import logging
from shapely.geometry import LineString
from app.services.geometry.road_edges import _safe_offset, NO_CURB_TYPES

logger = logging.getLogger(__name__)

CURB_WIDTH_M = 0.15

# Road types that get curbs
CURB_TYPES = {"primary", "secondary", "tertiary", "residential", "service"}


def generate_curbs(
    left_edge: LineString | None,
    right_edge: LineString | None,
    highway_type: str,
    name: str = "",
) -> tuple[LineString | None, LineString | None]:
    """Generate curb lines by offsetting road edges outward.

    Left curb = left edge offset +CURB_WIDTH (outward).
    Right curb = right edge offset -CURB_WIDTH (outward).

    Returns (left_curb, right_curb). Either may be None.
    Only generates curbs for appropriate road types.
    """
    if highway_type in NO_CURB_TYPES or highway_type not in CURB_TYPES:
        return None, None

    left_curb = None
    right_curb = None

    if left_edge is not None:
        left_curb = _safe_offset(left_edge, CURB_WIDTH_M, f"{name} left-curb")

    if right_edge is not None:
        right_curb = _safe_offset(right_edge, -CURB_WIDTH_M, f"{name} right-curb")

    return left_curb, right_curb
