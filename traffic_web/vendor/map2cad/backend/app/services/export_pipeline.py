"""Full export pipeline: polygon → Overpass → geometry → DXF → download."""

import logging
import time
import uuid

from flask import current_app

from app.errors import ExportError, OverpassError
from app.services.overpass_client import query_overpass
from app.services.osm_parser import parse_ways
from app.services.feature_parser import (
    parse_buildings,
    parse_landuse,
    parse_railways,
    parse_parking,
    parse_point_features,
    parse_cycleways,
    parse_utilities,
)
from app.services.geometry.projection import ProjectionHelper, resolve_epsg
from app.services.geometry.centerlines import build_centerlines, clip_centerlines
from app.services.geometry.road_builder import build_road_geometry
from app.services.geometry.feature_builder import build_feature_geometry
from app.services.geometry.intersections import (
    detect_intersections,
    generate_intersection_polygons,
    apply_turning_radii,
    trim_geometry_at_intersections,
)
from app.services.dxf_generator import generate_dxf
from app.services.file_manager import FileManager

logger = logging.getLogger(__name__)

# Feature layer option keys
FEATURE_LAYER_KEYS = (
    "buildings", "landuse", "railways", "parking",
    "traffic_signals", "street_furniture", "cycling", "utilities",
)


def _derive_enabled_layers(options: dict | None) -> dict[str, bool]:
    """Map user-facing option toggles to Overpass query layer flags."""
    opts = options or {}
    return {key: bool(opts.get(key, False)) for key in FEATURE_LAYER_KEYS}


def export(
    polygon_coords: list[list[float]],
    options: dict | None = None,
) -> dict:
    """Execute the full export pipeline.

    Args:
        polygon_coords: [[lng, lat], ...] selection polygon.
        options: Export options (layer toggles, etc.).

    Returns:
        dict with keys: download_url, filename, stats, warnings
    """
    start = time.time()
    request_id = uuid.uuid4().hex[:12]
    warnings: list[str] = []

    # File manager
    output_dir = current_app.config.get("TEMP_DIR", "output")
    fm = FileManager(output_dir)
    temp_dir = fm.create_temp_dir(request_id)

    try:
        # Step 1: Query Overpass (with feature layer flags)
        t0 = time.time()
        overpass_url = current_app.config.get("OVERPASS_API_URL")
        overpass_timeout = current_app.config.get("OVERPASS_TIMEOUT", 60)
        cache_dir = current_app.config.get("CACHE_DIR") if current_app.config.get("CACHE_ENABLED") else None
        cache_ttl = current_app.config.get("CACHE_TTL_SECONDS", 3600)
        enabled_layers = _derive_enabled_layers(options)
        result = query_overpass(
            polygon_coords, overpass_url, overpass_timeout,
            cache_dir=cache_dir, cache_ttl=cache_ttl,
            enabled_layers=enabled_layers,
        )
        all_ways = result["ways"]
        all_nodes = result["nodes"]
        logger.info(f"Step 1 - Overpass: {len(all_ways)} ways, {len(all_nodes)} nodes in {time.time()-t0:.2f}s")

        # Step 2: Parse road ways
        t0 = time.time()
        parsed_roads = parse_ways(all_ways)
        logger.info(f"Step 2 - Parse roads: {len(parsed_roads)} roads in {time.time()-t0:.2f}s")

        if not parsed_roads:
            # Only fail if no features at all were requested or found
            any_features = any(enabled_layers.values())
            if not any_features:
                raise ExportError("No roads found in the selected area", code="NO_ROADS_FOUND")
            warnings.append("No roads found in the selected area")

        # Step 3: Project coordinates
        t0 = time.time()
        centroid_lng = sum(c[0] for c in polygon_coords) / len(polygon_coords)
        centroid_lat = sum(c[1] for c in polygon_coords) / len(polygon_coords)
        crs_option = (options or {}).get("crs", "utm")
        target_epsg = resolve_epsg(crs_option, centroid_lng, centroid_lat)
        proj = ProjectionHelper(centroid_lng, centroid_lat, target_epsg=target_epsg)
        logger.info(f"Step 3 - Projection: EPSG:{proj.epsg} ({crs_option}) in {time.time()-t0:.2f}s")

        # Step 4: Build centerlines and clip
        t0 = time.time()
        boundary = proj.transform_polygon(polygon_coords)
        segments = []
        if parsed_roads:
            segments = build_centerlines(parsed_roads, proj)
            segments = clip_centerlines(segments, boundary)
        logger.info(f"Step 4 - Centerlines: {len(segments)} segments in {time.time()-t0:.2f}s")

        if not segments and not any(enabled_layers.values()):
            raise ExportError("No road segments within selection area", code="NO_ROADS_FOUND")

        # Step 5: Generate road geometry
        t0 = time.time()
        layers = {}
        if segments:
            layers, geom_warnings = build_road_geometry(segments, options)
            warnings.extend(geom_warnings)
        logger.info(f"Step 5 - Road geometry: {sum(len(v) for v in layers.values())} entities in {time.time()-t0:.2f}s")

        # Step 5b: Parse and build feature geometry
        t0 = time.time()
        polygon_layers = {}
        point_layers = {}
        feature_line_layers = {}
        feature_stats = {}

        try:
            buildings = parse_buildings(all_ways, proj, boundary) if enabled_layers.get("buildings") else []
            landuse_areas = parse_landuse(all_ways, proj, boundary) if enabled_layers.get("landuse") else []
            railway_lines = parse_railways(all_ways, proj, boundary) if enabled_layers.get("railways") else []
            parking_features = parse_parking(all_ways, all_nodes, proj, boundary) if enabled_layers.get("parking") else []
            point_features = parse_point_features(all_nodes, proj, boundary) if (
                enabled_layers.get("traffic_signals") or enabled_layers.get("street_furniture")
            ) else []
            cycleway_lines = parse_cycleways(all_ways, proj, boundary) if enabled_layers.get("cycling") else []
            utility_features = parse_utilities(all_ways, all_nodes, proj, boundary) if enabled_layers.get("utilities") else []

            feature_line_layers, polygon_layers, point_layers, feat_warnings = build_feature_geometry(
                buildings=buildings,
                landuse=landuse_areas,
                railways=railway_lines,
                parking=parking_features,
                points=point_features,
                cycleways=cycleway_lines,
                utilities=utility_features,
                options=options,
            )
            warnings.extend(feat_warnings)

            feature_stats = {
                "buildings_found": len(buildings),
                "landuse_areas": len(landuse_areas),
                "railways_found": len(railway_lines),
                "parking_found": len(parking_features),
                "point_features": len(point_features),
                "cycleways_found": len(cycleway_lines),
                "utilities_found": len(utility_features),
            }
        except Exception as e:
            logger.warning(f"Feature parsing failed, continuing with roads only: {e}")
            warnings.append(f"Feature parsing failed: {e}")

        # Merge feature line layers into main layers dict
        for k, v in feature_line_layers.items():
            if k in layers:
                layers[k].extend(v)
            else:
                layers[k] = v

        logger.info(f"Step 5b - Features: {sum(len(v) for v in polygon_layers.values())} polygons, "
                     f"{sum(len(v) for v in point_layers.values())} points in {time.time()-t0:.2f}s")

        # Step 6: Detect intersections
        t0 = time.time()
        try:
            intersections = detect_intersections(segments) if segments else []
            if intersections:
                intersections = generate_intersection_polygons(intersections, segments)
                intersections = apply_turning_radii(intersections)
            logger.info(f"Step 6 - Intersections: {len(intersections)} in {time.time()-t0:.2f}s")
        except Exception as e:
            logger.warning(f"Intersection detection failed, continuing without: {e}")
            intersections = []
            warnings.append(f"Intersection detection failed: {e}")

        # Step 7: Trim at intersections
        t0 = time.time()
        try:
            if intersections:
                layers = trim_geometry_at_intersections(layers, intersections)
        except Exception as e:
            logger.warning(f"Geometry trimming failed, continuing with untrimmed: {e}")
            warnings.append(f"Geometry trimming failed: {e}")
        logger.info(f"Step 7 - Trimming: done in {time.time()-t0:.2f}s")

        # Step 8: Generate DXF
        t0 = time.time()
        dxf_path = generate_dxf(
            layers=layers,
            polygon_layers=polygon_layers if polygon_layers else None,
            point_layers=point_layers if point_layers else None,
            intersections=intersections,
            boundary=boundary,
            output_dir=temp_dir,
        )
        logger.info(f"Step 8 - DXF: generated in {time.time()-t0:.2f}s")

        # Move to downloads
        filename = fm.move_to_downloads(dxf_path)

        # Cleanup stale files
        fm.cleanup_stale_files()

        total_time = time.time() - start

        all_layer_keys = list(layers.keys())
        if polygon_layers:
            all_layer_keys.extend(polygon_layers.keys())
        if point_layers:
            all_layer_keys.extend(point_layers.keys())

        total_entities = (
            sum(len(v) for v in layers.values())
            + sum(len(v) for v in polygon_layers.values())
            + sum(len(v) for v in point_layers.values())
        )

        stats = {
            "roads_found": len(parsed_roads),
            "roads_processed": len(segments),
            "intersections_detected": len(intersections),
            "layers_generated": all_layer_keys,
            "entities_total": total_entities,
            "format": "dxf",
            "time_seconds": round(total_time, 2),
            **feature_stats,
        }

        logger.info(f"Export complete: {filename} in {total_time:.2f}s")

        return {
            "download_url": f"/downloads/{filename}",
            "filename": filename,
            "stats": stats,
            "warnings": warnings,
        }

    except (ExportError, OverpassError):
        raise
    except Exception as e:
        logger.exception(f"Export pipeline failed: {e}")
        raise ExportError(f"Export failed: {e}", code="EXPORT_FAILED")
    finally:
        fm.cleanup_temp_dir(temp_dir)
