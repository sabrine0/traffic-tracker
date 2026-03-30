"""Unit tests for app.validators module."""

import math
import pytest
from app.validators import validate_polygon, validate_area, validate_options
from app.errors import ValidationError


# --- validate_polygon ---

class TestValidatePolygon:
    def test_valid_triangle(self):
        result = validate_polygon([[0, 0], [1, 0], [0, 1]])
        assert len(result) == 3

    def test_valid_square(self):
        result = validate_polygon([[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]])
        assert len(result) == 4
    
    def test_accepts_closed_square_with_repeated_last_vertex(self):
        result = validate_polygon([
            [-73.99, 40.75],
            [-73.98, 40.75],
            [-73.98, 40.76],
            [-73.99, 40.76],
            [-73.99, 40.75],
        ])
        assert result == [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]]

    def test_accepts_polygon_with_duplicate_ui_vertex(self):
        result = validate_polygon([
            [-73.99, 40.75],
            [-73.99, 40.76],
            [-73.98, 40.76],
            [-73.99, 40.76],
            [-73.98, 40.75],
        ])
        assert result == [[-73.99, 40.75], [-73.99, 40.76], [-73.98, 40.76], [-73.98, 40.75]]

    def test_rejects_non_list(self):
        with pytest.raises(ValidationError, match="array"):
            validate_polygon("not a list")

    def test_rejects_too_few_vertices(self):
        with pytest.raises(ValidationError, match="at least 3"):
            validate_polygon([[0, 0], [1, 1]])

    def test_rejects_too_many_vertices(self):
        polygon = [[i * 0.0001, i * 0.0001] for i in range(1001)]
        with pytest.raises(ValidationError, match="1000"):
            validate_polygon(polygon)

    def test_rejects_bad_vertex_format(self):
        with pytest.raises(ValidationError, match="must be"):
            validate_polygon([[0, 0], [1], [0, 1]])

    def test_rejects_non_numeric_coords(self):
        with pytest.raises(ValidationError, match="numbers"):
            validate_polygon([["a", "b"], [0, 0], [1, 1]])

    def test_rejects_nan(self):
        with pytest.raises(ValidationError, match="NaN"):
            validate_polygon([[float("nan"), 0], [0, 0], [1, 1]])

    def test_rejects_inf(self):
        with pytest.raises(ValidationError, match="Infinity"):
            validate_polygon([[float("inf"), 0], [0, 0], [1, 1]])

    def test_rejects_longitude_out_of_range(self):
        with pytest.raises(ValidationError, match="longitude out of range"):
            validate_polygon([[200, 0], [0, 0], [1, 1]])

    def test_rejects_latitude_out_of_range(self):
        with pytest.raises(ValidationError, match="latitude out of range"):
            validate_polygon([[0, 100], [0, 0], [1, 1]])

    def test_rejects_self_intersecting(self):
        # Bowtie
        with pytest.raises(ValidationError, match="self-intersecting"):
            validate_polygon([[0, 0], [1, 1], [1, 0], [0, 1]])

    def test_returns_cleaned_coords(self):
        result = validate_polygon([[10.5, 20.3], [11.5, 20.3], [11.0, 21.0]])
        assert result == [[10.5, 20.3], [11.5, 20.3], [11.0, 21.0]]


# --- validate_area ---

class TestValidateArea:
    def test_small_area_passes(self):
        coords = [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]]
        area = validate_area(coords, 25)
        assert area > 0

    def test_huge_area_rejected(self):
        coords = [[-74.5, 40.0], [-73.5, 40.0], [-73.5, 41.0], [-74.5, 41.0]]
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_area(coords, 25)

    def test_returns_positive_area(self):
        coords = [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]]
        area = validate_area(coords, 100)
        assert area > 0


# --- validate_options ---

class TestValidateOptions:
    def test_none_returns_defaults(self):
        result = validate_options(None)
        # Road layers default to True
        assert result["lane_markings"] is True
        assert result["sidewalks"] is True
        # Feature layers default to False
        assert result["buildings"] is False
        assert result["railways"] is False

    def test_non_dict_returns_defaults(self):
        result = validate_options("invalid")
        assert result["lane_markings"] is True
        assert result["buildings"] is False

    def test_partial_overrides(self):
        result = validate_options({"lane_markings": False})
        assert result["lane_markings"] is False
        assert result["sidewalks"] is True

    def test_all_false(self):
        result = validate_options({
            "lane_markings": False,
            "sidewalks": False,
            "curbs": False,
            "intersections": False,
            "road_names": False,
        })
        bool_keys = ["lane_markings", "sidewalks", "curbs", "intersections", "road_names"]
        assert all(result[k] is False for k in bool_keys)

    def test_extra_keys_ignored(self):
        result = validate_options({"unknown_key": True, "lane_markings": False})
        assert "unknown_key" not in result
        assert result["lane_markings"] is False

    def test_truthy_values_coerced(self):
        result = validate_options({"lane_markings": 1, "sidewalks": 0})
        assert result["lane_markings"] is True
        assert result["sidewalks"] is False

    def test_feature_layers_default_false(self):
        result = validate_options({})
        for key in ("buildings", "landuse", "railways", "parking",
                    "traffic_signals", "street_furniture", "cycling", "utilities"):
            assert result[key] is False

    def test_feature_layers_can_enable(self):
        result = validate_options({"buildings": True, "railways": True})
        assert result["buildings"] is True
        assert result["railways"] is True
        assert result["parking"] is False
