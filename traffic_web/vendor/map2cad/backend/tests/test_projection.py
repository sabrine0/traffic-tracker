import pytest
from app.services.geometry.projection import get_utm_epsg, ProjectionHelper


def test_paris_utm_zone():
    assert get_utm_epsg(2.35, 48.86) == 32631  # Zone 31N


def test_new_york_utm_zone():
    assert get_utm_epsg(-73.98, 40.75) == 32618  # Zone 18N


def test_tokyo_utm_zone():
    assert get_utm_epsg(139.7, 35.68) == 32654  # Zone 54N


def test_sydney_utm_zone():
    assert get_utm_epsg(151.2, -33.87) == 32756  # Zone 56S


def test_roundtrip_accuracy():
    proj = ProjectionHelper(2.35, 48.86)
    lon, lat = 2.3522, 48.8566
    x, y = proj.to_utm(lon, lat)
    lon2, lat2 = proj.to_wgs84(x, y)
    assert abs(lon - lon2) < 0.0001
    assert abs(lat - lat2) < 0.0001


def test_utm_output_in_meters():
    proj = ProjectionHelper(2.35, 48.86)
    x, y = proj.to_utm(2.35, 48.86)
    assert x > 100_000  # UTM easting in 100k+ range
    assert y > 1_000_000  # UTM northing in 1M+ range


def test_transform_coords():
    proj = ProjectionHelper(-73.98, 40.75)
    nodes = [
        {"lat": 40.750, "lon": -73.990},
        {"lat": 40.751, "lon": -73.990},
        {"lat": 40.752, "lon": -73.990},
    ]
    utm = proj.transform_coords(nodes)
    assert len(utm) == 3
    # All should be in meters (not degrees)
    for x, y in utm:
        assert x > 100_000
        assert y > 1_000_000


def test_transform_polygon():
    proj = ProjectionHelper(-73.98, 40.75)
    coords = [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]]
    poly = proj.transform_polygon(coords)
    assert poly.is_valid
    assert poly.area > 0
    # Roughly 1km x 1km area, so area should be ~1,000,000 m²
    assert 500_000 < poly.area < 2_000_000
    # Should be closed (len(exterior.coords) = vertices + 1 for closure)
    assert len(poly.exterior.coords) == 5
