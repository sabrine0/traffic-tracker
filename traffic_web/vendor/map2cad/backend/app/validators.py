import math
from shapely.geometry import Polygon
from app.errors import ValidationError


def _normalize_coords(coords: list[list[float]]) -> list[list[float]]:
    """Drop duplicate vertices that can appear in UI-generated polygons."""
    normalized: list[list[float]] = []
    seen: set[tuple[float, float]] = set()

    for lng, lat in coords:
        key = (lng, lat)
        if normalized and key == (normalized[-1][0], normalized[-1][1]):
            continue
        if key in seen:
            continue
        normalized.append([lng, lat])
        seen.add(key)

    if len(normalized) > 1 and normalized[0] == normalized[-1]:
        normalized.pop()

    return normalized


def validate_polygon(polygon_data: list) -> list[list[float]]:
    """Validate and return a polygon as list of [lng, lat] pairs."""
    if not isinstance(polygon_data, list):
        raise ValidationError("Polygon must be an array of [lng, lat] pairs", code="INVALID_POLYGON")

    if len(polygon_data) < 3:
        raise ValidationError("Polygon must have at least 3 vertices", code="INVALID_POLYGON")

    if len(polygon_data) > 1000:
        raise ValidationError("Polygon must have at most 1000 vertices", code="INVALID_POLYGON")

    coords = []
    for i, point in enumerate(polygon_data):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValidationError(f"Vertex {i} must be [lng, lat]", code="INVALID_POLYGON")

        lng, lat = point
        if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
            raise ValidationError(f"Vertex {i} coordinates must be numbers", code="INVALID_POLYGON")

        if math.isnan(lng) or math.isnan(lat) or math.isinf(lng) or math.isinf(lat):
            raise ValidationError(f"Vertex {i} contains NaN or Infinity", code="INVALID_POLYGON")

        if not (-180 <= lng <= 180):
            raise ValidationError(f"Vertex {i} longitude out of range (-180 to 180)", code="INVALID_POLYGON")

        if not (-90 <= lat <= 90):
            raise ValidationError(f"Vertex {i} latitude out of range (-90 to 90)", code="INVALID_POLYGON")

        coords.append([lng, lat])

    coords = _normalize_coords(coords)

    if len(coords) < 3:
        raise ValidationError("Polygon must have at least 3 distinct vertices", code="INVALID_POLYGON")

    shapely_poly = Polygon(coords)
    if not shapely_poly.is_valid:
        raise ValidationError("Polygon is self-intersecting or invalid", code="INVALID_POLYGON")
    if shapely_poly.is_empty or shapely_poly.area == 0:
        raise ValidationError("Polygon area must be greater than zero", code="INVALID_POLYGON")

    return coords


def validate_area(polygon_coords: list[list[float]], max_area_km2: float) -> float:
    """Validate area does not exceed maximum. Returns area in km²."""
    shapely_poly = Polygon(polygon_coords)

    # Approximate area in km² using the polygon in degrees
    # More accurate calculation happens later with UTM projection
    # For validation, use a rough estimate: 1 degree ≈ 111 km
    bounds = shapely_poly.bounds  # (minx, miny, maxx, maxy)
    width_km = (bounds[2] - bounds[0]) * 111 * math.cos(math.radians((bounds[1] + bounds[3]) / 2))
    height_km = (bounds[3] - bounds[1]) * 111
    rough_area = width_km * height_km

    if rough_area > max_area_km2 * 2:  # generous check since this is rough
        raise ValidationError(
            f"Selected area (~{rough_area:.1f} km²) exceeds maximum of {max_area_km2} km²",
            code="AREA_TOO_LARGE",
        )

    return rough_area


def validate_options(options_data: dict | None) -> dict:
    """Validate export options. Returns sanitized options dict."""
    defaults = {
        # Road layers (default on)
        "lane_markings": True,
        "sidewalks": True,
        "curbs": True,
        "intersections": True,
        "road_names": True,
        # Feature layers (default off)
        "buildings": False,
        "landuse": False,
        "railways": False,
        "parking": False,
        "traffic_signals": False,
        "street_furniture": False,
        "cycling": False,
        "utilities": False,
    }

    if options_data is None:
        return defaults

    if not isinstance(options_data, dict):
        return defaults

    result = {}
    for key, default_val in defaults.items():
        val = options_data.get(key, default_val)
        result[key] = bool(val)

    # Format is always DXF
    result["format"] = "dxf"

    # CRS option
    valid_crs = ("utm", "lambert93", "lambert_nord", "lambert_sud", "lambert_cc46", "lambert_cc47")
    crs = options_data.get("crs", "utm")
    if crs not in valid_crs:
        crs = "utm"
    result["crs"] = crs

    return result
