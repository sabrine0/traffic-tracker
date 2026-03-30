"""Generate sidewalk edge polylines by offsetting curb lines outward."""

import logging
from shapely.geometry import LineString
from app.services.geometry.road_edges import _safe_offset

logger = logging.getLogger(__name__)

# Sidewalk widths by classification
SIDEWALK_WIDTH = {
    "main": 2.0,       # primary, secondary, trunk
    "secondary": 1.8,  # tertiary
    "local": 1.5,      # residential, service
}

# Road types that never get sidewalks
NO_SIDEWALK_TYPES = {"motorway", "trunk", "track"}


def generate_sidewalks(
    left_curb: LineString | None,
    right_curb: LineString | None,
    highway_type: str,
    classification: str,
    sidewalk_tag: str,
    name: str = "",
) -> tuple[LineString | None, LineString | None]:
    """Generate sidewalk outer edges by offsetting curb lines outward.

    sidewalk_tag: "both", "left", "right", or "no"
    Returns (left_sidewalk, right_sidewalk). Either may be None.
    """
    if highway_type in NO_SIDEWALK_TYPES:
        return None, None

    if sidewalk_tag == "no":
        return None, None

    sw_width = SIDEWALK_WIDTH.get(classification, 1.5)

    left_sw = None
    right_sw = None

    if sidewalk_tag in ("both", "left") and left_curb is not None:
        left_sw = _safe_offset(left_curb, sw_width, f"{name} left-sidewalk")

    if sidewalk_tag in ("both", "right") and right_curb is not None:
        right_sw = _safe_offset(right_curb, -sw_width, f"{name} right-sidewalk")

    return left_sw, right_sw
