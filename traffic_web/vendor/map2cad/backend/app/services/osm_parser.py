from dataclasses import dataclass, field
from app.config import ROAD_WIDTH_DEFAULTS, DEFAULT_ROAD


@dataclass
class RoadSegment:
    way_id: int
    name: str
    highway_type: str
    classification: str
    width_m: float
    lanes: int
    lane_width_m: float
    oneway: bool
    sidewalk: str  # "both", "left", "right", "no"
    has_median: bool
    nodes: list[dict] = field(default_factory=list)  # [{lat, lon}, ...]


def parse_highway_type(tags: dict) -> str:
    """Get the highway type, stripping _link suffix."""
    hw = tags.get("highway", "")
    return hw.replace("_link", "")


def parse_lanes(tags: dict, default_lanes: int) -> int:
    """Parse lanes tag, return int."""
    raw = tags.get("lanes")
    if raw is not None:
        try:
            return max(1, int(raw))
        except (ValueError, TypeError):
            pass
    return default_lanes


def parse_width(tags: dict, lanes: int, lane_width: float) -> float:
    """Parse width tag (meters), or calculate from lanes."""
    raw = tags.get("width")
    if raw is not None:
        try:
            # Handle formats like "8", "8m", "8.5 m"
            cleaned = raw.replace("m", "").strip()
            return max(2.0, float(cleaned))
        except (ValueError, TypeError):
            pass
    return lanes * lane_width


def parse_oneway(tags: dict) -> bool:
    """Parse oneway tag."""
    val = tags.get("oneway", "no")
    return val in ("yes", "1", "-1")


def parse_sidewalk(tags: dict, default_sidewalk: str) -> str:
    """Parse sidewalk tag."""
    val = tags.get("sidewalk", default_sidewalk)
    if val in ("both", "left", "right", "no", "none"):
        return "no" if val == "none" else val
    return default_sidewalk


def is_divided(tags: dict, highway_type: str, defaults: dict) -> bool:
    """Check if road is divided (has median)."""
    if tags.get("dual_carriageway") == "yes":
        return True
    if tags.get("divider") in ("yes", "median"):
        return True
    return defaults.get("divided", False)


def parse_ways(ways: list[dict]) -> list[RoadSegment]:
    """Parse Overpass way data into RoadSegment objects."""
    segments = []

    for way in ways:
        tags = way.get("tags", {})
        nodes = way.get("nodes", [])

        if len(nodes) < 2:
            continue

        # Only parse ways with a highway tag
        if "highway" not in tags:
            continue

        highway_type = parse_highway_type(tags)
        defaults = ROAD_WIDTH_DEFAULTS.get(highway_type, DEFAULT_ROAD)

        lanes = parse_lanes(tags, defaults["lanes"])
        lane_width = defaults["lane_width"]
        width = parse_width(tags, lanes, lane_width)
        oneway = parse_oneway(tags)
        sidewalk = parse_sidewalk(tags, defaults["sidewalk"])
        divided = is_divided(tags, highway_type, defaults)

        # Reverse node order for oneway=-1 (travel direction opposite to way direction)
        if tags.get("oneway") == "-1":
            nodes = list(reversed(nodes))

        segment = RoadSegment(
            way_id=way["id"],
            name=tags.get("name", ""),
            highway_type=highway_type,
            classification=defaults["classification"],
            width_m=width,
            lanes=lanes,
            lane_width_m=lane_width,
            oneway=oneway,
            sidewalk=sidewalk,
            has_median=divided,
            nodes=nodes,
        )
        segments.append(segment)

    return segments
