"""Construct and clip road centerline geometries."""

import logging
from shapely.geometry import LineString, MultiLineString, GeometryCollection, Polygon
from shapely.validation import make_valid
from app.services.osm_parser import RoadSegment as ParsedRoad
from app.services.geometry.models import RoadSegment
from app.services.geometry.projection import ProjectionHelper

logger = logging.getLogger(__name__)

MIN_LENGTH_M = 1.0


def build_centerlines(
    parsed_roads: list[ParsedRoad],
    proj: ProjectionHelper,
) -> list[RoadSegment]:
    """Convert parsed OSM roads into RoadSegment objects with UTM LineString centerlines."""
    segments = []

    for road in parsed_roads:
        if len(road.nodes) < 2:
            logger.warning(f"Skipping way {road.way_id}: fewer than 2 nodes")
            continue

        utm_coords = proj.transform_coords(road.nodes)

        if len(utm_coords) < 2:
            continue

        line = LineString(utm_coords)

        if line.is_empty or line.length < MIN_LENGTH_M:
            continue

        seg = RoadSegment(
            centerline=line,
            name=road.name,
            highway_type=road.highway_type,
            classification=road.classification,
            width_m=road.width_m,
            lanes=road.lanes,
            lane_width_m=road.lane_width_m,
            oneway=road.oneway,
            sidewalk=road.sidewalk,
            has_median=road.has_median,
        )
        segments.append(seg)

    logger.info(f"Built {len(segments)} centerlines from {len(parsed_roads)} parsed roads")
    return segments


def clip_centerlines(
    segments: list[RoadSegment],
    boundary: Polygon,
) -> list[RoadSegment]:
    """Clip road centerlines to the selection polygon boundary."""
    clipped = []

    for seg in segments:
        try:
            result = seg.centerline.intersection(boundary)
        except Exception as e:
            logger.warning(f"Intersection failed for {seg.name}: {e}")
            continue

        lines = _extract_lines(result)

        for line in lines:
            line = _validate_and_clean(line)
            if line is None:
                continue

            new_seg = RoadSegment(
                centerline=line,
                name=seg.name,
                highway_type=seg.highway_type,
                classification=seg.classification,
                width_m=seg.width_m,
                lanes=seg.lanes,
                lane_width_m=seg.lane_width_m,
                oneway=seg.oneway,
                sidewalk=seg.sidewalk,
                has_median=seg.has_median,
            )
            clipped.append(new_seg)

    removed = len(segments) - len(clipped)
    if removed > 0:
        logger.info(f"Clipping: {len(clipped)} segments kept, {removed} removed/split")

    return clipped


def _extract_lines(geom) -> list[LineString]:
    """Extract LineString geometries from various geometry types."""
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


def _validate_and_clean(line: LineString) -> LineString | None:
    """Validate and clean a LineString geometry."""
    if line.is_empty:
        return None

    if not line.is_valid:
        try:
            line = make_valid(line)
            if not isinstance(line, LineString):
                return None
        except Exception:
            return None

    # Remove duplicate vertices
    line = line.simplify(0, preserve_topology=True)

    if line.length < MIN_LENGTH_M:
        return None

    return line
