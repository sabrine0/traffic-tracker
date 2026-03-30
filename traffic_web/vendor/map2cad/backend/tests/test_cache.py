"""Tests for Overpass response caching."""

import json
import os
import time
from unittest.mock import patch, MagicMock

import pytest

from app.services.overpass_client import (
    _cache_key,
    _read_cache,
    _write_cache,
    cleanup_stale_cache,
    query_overpass,
)


POLYGON = [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.76]]
SAMPLE_WAYS = [{"id": 1, "nodes": [{"lat": 40.75, "lon": -73.99}], "tags": {"highway": "residential"}}]


class TestCacheKey:
    def test_deterministic(self):
        assert _cache_key(POLYGON) == _cache_key(POLYGON)

    def test_different_polygons_different_keys(self):
        other = [[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.77], [-73.99, 40.77]]
        assert _cache_key(POLYGON) != _cache_key(other)

    def test_order_independent(self):
        # Sorted internally, so different input order → same key
        reversed_poly = list(reversed(POLYGON))
        assert _cache_key(POLYGON) == _cache_key(reversed_poly)


class TestCacheReadWrite:
    def test_write_then_read(self, tmp_path):
        key = "test123"
        _write_cache(str(tmp_path), key, SAMPLE_WAYS)
        result = _read_cache(str(tmp_path), key, ttl=3600)
        assert result == SAMPLE_WAYS

    def test_read_nonexistent(self, tmp_path):
        assert _read_cache(str(tmp_path), "missing", ttl=3600) is None

    def test_expired_cache_returns_none(self, tmp_path):
        key = "expired"
        _write_cache(str(tmp_path), key, SAMPLE_WAYS)
        # Set mtime to 2 hours ago
        path = os.path.join(str(tmp_path), f"{key}.json")
        old_time = time.time() - 7200
        os.utime(path, (old_time, old_time))
        assert _read_cache(str(tmp_path), key, ttl=3600) is None

    def test_corrupted_cache_returns_none(self, tmp_path):
        key = "corrupt"
        path = os.path.join(str(tmp_path), f"{key}.json")
        with open(path, "w") as f:
            f.write("not valid json{{{")
        assert _read_cache(str(tmp_path), key, ttl=3600) is None


class TestCleanupStaleCache:
    def test_removes_expired(self, tmp_path):
        # Create 2 files: one fresh, one stale
        fresh = os.path.join(str(tmp_path), "fresh.json")
        stale = os.path.join(str(tmp_path), "stale.json")
        with open(fresh, "w") as f:
            json.dump([], f)
        with open(stale, "w") as f:
            json.dump([], f)
        old_time = time.time() - 7200
        os.utime(stale, (old_time, old_time))

        removed = cleanup_stale_cache(str(tmp_path), ttl=3600)
        assert removed == 1
        assert os.path.exists(fresh)
        assert not os.path.exists(stale)

    def test_nonexistent_dir(self):
        assert cleanup_stale_cache("/nonexistent/path", ttl=3600) == 0


class TestQueryOverpassWithCache:
    def _mock_response(self):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "elements": [
                {"type": "node", "id": 1, "lat": 40.75, "lon": -73.99},
                {"type": "node", "id": 2, "lat": 40.76, "lon": -73.98},
                {"type": "way", "id": 100, "nodes": [1, 2], "tags": {"highway": "residential", "name": "Test St"}},
            ]
        }
        mock.raise_for_status = MagicMock()
        return mock

    def test_cache_miss_then_hit(self, tmp_path):
        with patch("app.services.overpass_client.requests.post", return_value=self._mock_response()) as mock_post:
            # First call: cache miss
            result1 = query_overpass(POLYGON, cache_dir=str(tmp_path), cache_ttl=3600)
            assert len(result1["ways"]) == 1
            assert mock_post.call_count == 1

            # Second call: cache hit — no network call
            result2 = query_overpass(POLYGON, cache_dir=str(tmp_path), cache_ttl=3600)
            assert result2 == result1
            assert mock_post.call_count == 1  # no additional call

    def test_no_cache_when_disabled(self, tmp_path):
        with patch("app.services.overpass_client.requests.post", return_value=self._mock_response()) as mock_post:
            query_overpass(POLYGON, cache_dir=None)
            query_overpass(POLYGON, cache_dir=None)
            assert mock_post.call_count == 2
