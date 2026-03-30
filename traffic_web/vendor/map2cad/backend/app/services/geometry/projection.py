"""Coordinate projection utilities (UTM, Lambert, etc.)."""

from pyproj import Transformer
from shapely.geometry import Polygon


CRS_EPSG_MAP: dict[str, int] = {
    "lambert93": 2154,
    "lambert_nord": 27561,
    "lambert_sud": 27563,
    "lambert_cc46": 3946,
    "lambert_cc47": 3947,
}


def get_utm_epsg(lon: float, lat: float) -> int:
    """Compute UTM EPSG code from a point's longitude and latitude."""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def resolve_epsg(crs_option: str, centroid_lon: float, centroid_lat: float) -> int:
    """Resolve a CRS option string to an EPSG code."""
    if crs_option == "utm" or crs_option not in CRS_EPSG_MAP:
        return get_utm_epsg(centroid_lon, centroid_lat)
    return CRS_EPSG_MAP[crs_option]


class ProjectionHelper:
    """Handles WGS84 <-> projected coordinate transformations."""

    def __init__(self, centroid_lon: float, centroid_lat: float, target_epsg: int | None = None):
        self.epsg = target_epsg if target_epsg is not None else get_utm_epsg(centroid_lon, centroid_lat)
        self._to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{self.epsg}", always_xy=True)
        self._to_wgs = Transformer.from_crs(f"EPSG:{self.epsg}", "EPSG:4326", always_xy=True)

    def to_utm(self, lon: float, lat: float) -> tuple[float, float]:
        """Transform a single point from WGS84 to UTM."""
        return self._to_utm.transform(lon, lat)

    def to_wgs84(self, x: float, y: float) -> tuple[float, float]:
        """Transform a single point from UTM back to WGS84."""
        return self._to_wgs.transform(x, y)

    def transform_coords(self, coords: list[dict]) -> list[tuple[float, float]]:
        """Transform a list of {lat, lon} dicts to UTM (x, y) tuples."""
        return [self.to_utm(c["lon"], c["lat"]) for c in coords]

    def transform_polygon(self, polygon_coords: list[list[float]]) -> Polygon:
        """Transform a selection polygon [[lng, lat], ...] to a UTM Shapely Polygon."""
        utm_coords = [self.to_utm(lng, lat) for lng, lat in polygon_coords]
        # Close the ring
        if utm_coords[0] != utm_coords[-1]:
            utm_coords.append(utm_coords[0])
        return Polygon(utm_coords)
