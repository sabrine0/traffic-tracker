"""Orchestrate all road geometry generation and group by layer."""

import logging
from shapely.geometry import LineString
from app.services.geometry.models import RoadSegment
from app.services.geometry.road_edges import generate_road_edges, generate_divided_road_edges
from app.services.geometry.lane_markings import generate_lane_markings, generate_carriageway_lane_markings
from app.services.geometry.curbs import generate_curbs
from app.services.geometry.sidewalks import generate_sidewalks

logger = logging.getLogger(__name__)

# Layer names
ROAD_EDGES = "ROAD_EDGES"
CENTERLINES = "CENTERLINES"
LANE_MARKINGS = "LANE_MARKINGS"
CURBS = "CURBS"
SIDEWALKS = "SIDEWALKS"
MEDIANS = "MEDIANS"

# Default export options
DEFAULT_OPTIONS = {
    "road_edges": True,
    "centerlines": True,
    "lane_markings": True,
    "curbs": True,
    "sidewalks": True,
    "medians": True,
}

GeometryEntry = tuple[LineString, dict]  # (geometry, metadata)
LayerDict = dict[str, list[GeometryEntry]]


def build_road_geometry(
    segments: list[RoadSegment],
    options: dict | None = None,
) -> tuple[LayerDict, list[str]]:
    """Build all road geometry grouped by target layer.

    Args:
        segments: List of RoadSegment objects with UTM centerlines.
        options: Export options dict. Keys match DEFAULT_OPTIONS.

    Returns:
        (layers, warnings) where layers is {layer_name: [(geometry, metadata), ...]}
        and warnings is a list of warning messages.
    """
    opts = {**DEFAULT_OPTIONS, **(options or {})}
    layers: LayerDict = {}
    warnings: list[str] = []
    processed = 0
    skipped = 0

    for seg in segments:
        try:
            _process_segment(seg, opts, layers)
            processed += 1
        except Exception as e:
            skipped += 1
            msg = f"Skipped road '{seg.name}': {e}"
            warnings.append(msg)
            logger.warning(msg)

    # Log stats
    logger.info(
        f"Road geometry: {processed} processed, {skipped} skipped. "
        f"Layers: {', '.join(f'{k}={len(v)}' for k, v in layers.items())}"
    )

    return layers, warnings


def _process_segment(
    seg: RoadSegment,
    opts: dict,
    layers: LayerDict,
) -> None:
    """Process a single road segment into all geometry layers."""
    if seg.centerline.is_empty or len(seg.centerline.coords) < 2:
        raise ValueError("Empty or degenerate centerline")

    meta = {"name": seg.name, "highway_type": seg.highway_type}

    # Centerline always added if enabled
    if opts.get("centerlines"):
        _add(layers, CENTERLINES, seg.centerline, {**meta, "linetype": "dashdot"})

    if seg.has_median:
        _process_divided_road(seg, opts, layers, meta)
    else:
        _process_simple_road(seg, opts, layers, meta)


def _process_simple_road(
    seg: RoadSegment,
    opts: dict,
    layers: LayerDict,
    meta: dict,
) -> None:
    """Process a non-divided road."""
    left_edge, right_edge = generate_road_edges(seg)

    # Road edges
    if opts.get("road_edges"):
        if left_edge:
            _add(layers, ROAD_EDGES, left_edge, {**meta, "side": "left"})
        if right_edge:
            _add(layers, ROAD_EDGES, right_edge, {**meta, "side": "right"})

    # Lane markings
    if opts.get("lane_markings"):
        markings = generate_lane_markings(seg)
        for line, linetype in markings:
            _add(layers, LANE_MARKINGS, line, {**meta, "linetype": linetype})

    # Curbs
    if opts.get("curbs"):
        left_curb, right_curb = generate_curbs(
            left_edge, right_edge, seg.highway_type, seg.name
        )
        if left_curb:
            _add(layers, CURBS, left_curb, {**meta, "side": "left"})
        if right_curb:
            _add(layers, CURBS, right_curb, {**meta, "side": "right"})

        # Sidewalks (depend on curbs)
        if opts.get("sidewalks"):
            left_sw, right_sw = generate_sidewalks(
                left_curb, right_curb,
                seg.highway_type, seg.classification,
                seg.sidewalk, seg.name,
            )
            if left_sw:
                _add(layers, SIDEWALKS, left_sw, {**meta, "side": "left"})
            if right_sw:
                _add(layers, SIDEWALKS, right_sw, {**meta, "side": "right"})


def _process_divided_road(
    seg: RoadSegment,
    opts: dict,
    layers: LayerDict,
    meta: dict,
) -> None:
    """Process a divided road with median."""
    result = generate_divided_road_edges(seg)

    left_edges = result["left_carriageway_edges"]
    right_edges = result["right_carriageway_edges"]
    median_lines = result["median_lines"]

    # Road edges for each carriageway
    if opts.get("road_edges"):
        for edge in left_edges:
            if edge:
                _add(layers, ROAD_EDGES, edge, {**meta, "carriageway": "left"})
        for edge in right_edges:
            if edge:
                _add(layers, ROAD_EDGES, edge, {**meta, "carriageway": "right"})

    # Median lines
    if opts.get("medians"):
        for line in median_lines:
            if line:
                _add(layers, MEDIANS, line, {**meta})

    # Lane markings per carriageway
    if opts.get("lane_markings"):
        left_cl = result.get("left_centerline")
        right_cl = result.get("right_centerline")
        if left_cl:
            markings = generate_carriageway_lane_markings(
                left_cl,
                result["left_carriageway_width"],
                result["left_carriageway_lanes"],
                seg.lane_width_m,
                f"{seg.name} left-cw",
            )
            for line, linetype in markings:
                _add(layers, LANE_MARKINGS, line, {**meta, "linetype": linetype})
        if right_cl:
            markings = generate_carriageway_lane_markings(
                right_cl,
                result["right_carriageway_width"],
                result["right_carriageway_lanes"],
                seg.lane_width_m,
                f"{seg.name} right-cw",
            )
            for line, linetype in markings:
                _add(layers, LANE_MARKINGS, line, {**meta, "linetype": linetype})

    # Curbs and sidewalks for outer edges
    if opts.get("curbs"):
        outer_left = left_edges[0]
        outer_right = right_edges[1]
        left_curb, right_curb = generate_curbs(
            outer_left, outer_right, seg.highway_type, seg.name
        )
        if left_curb:
            _add(layers, CURBS, left_curb, {**meta, "side": "left"})
        if right_curb:
            _add(layers, CURBS, right_curb, {**meta, "side": "right"})

        if opts.get("sidewalks"):
            left_sw, right_sw = generate_sidewalks(
                left_curb, right_curb,
                seg.highway_type, seg.classification,
                seg.sidewalk, seg.name,
            )
            if left_sw:
                _add(layers, SIDEWALKS, left_sw, {**meta, "side": "left"})
            if right_sw:
                _add(layers, SIDEWALKS, right_sw, {**meta, "side": "right"})


def _add(layers: LayerDict, layer: str, geom: LineString, meta: dict) -> None:
    """Add a geometry entry to a layer."""
    if layer not in layers:
        layers[layer] = []
    layers[layer].append((geom, meta))
