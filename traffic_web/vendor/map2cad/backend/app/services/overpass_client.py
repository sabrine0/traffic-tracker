import hashlib
import json
import os
import time
import logging
import requests
from app.errors import OverpassError

logger = logging.getLogger(__name__)


def _cache_key(polygon_coords: list[list[float]], enabled_layers: dict[str, bool] | None = None) -> str:
    """Generate a cache key from polygon coordinates and enabled layers."""
    # Round to 6 decimals and sort for consistency
    rounded = sorted([round(lng, 6), round(lat, 6)] for lng, lat in polygon_coords)
    key_data = {"coords": rounded}
    if enabled_layers:
        key_data["layers"] = sorted(k for k, v in enabled_layers.items() if v)
    raw = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _read_cache(cache_dir: str, key: str, ttl: int) -> dict | None:
    """Read cached Overpass response if valid."""
    path = os.path.join(cache_dir, f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        age = time.time() - os.path.getmtime(path)
        if age > ttl:
            logger.info(f"Cache expired for {key} (age={age:.0f}s, ttl={ttl}s)")
            os.remove(path)
            return None
        with open(path) as f:
            data = json.load(f)
        logger.info(f"Cache hit for {key} (age={age:.0f}s)")
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Cache read error for {key}: {e}")
        return None


def _write_cache(cache_dir: str, key: str, data: dict) -> None:
    """Write Overpass response to cache."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, f"{key}.json")
        with open(path, "w") as f:
            json.dump(data, f)
        logger.info(f"Cached response for {key}")
    except OSError as e:
        logger.warning(f"Cache write error for {key}: {e}")


def cleanup_stale_cache(cache_dir: str, ttl: int) -> int:
    """Remove expired cache files. Returns number of files removed."""
    if not os.path.isdir(cache_dir):
        return 0
    removed = 0
    now = time.time()
    try:
        for fname in os.listdir(cache_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(cache_dir, fname)
            try:
                if now - os.path.getmtime(path) > ttl:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    if removed:
        logger.info(f"Cleaned up {removed} stale cache files")
    return removed


def build_overpass_query(
    polygon_coords: list[list[float]],
    timeout: int = 60,
    enabled_layers: dict[str, bool] | None = None,
) -> str:
    """Build Overpass QL query for features within a polygon.

    Args:
        polygon_coords: List of [lng, lat] pairs
        timeout: Query timeout in seconds
        enabled_layers: Dict of layer toggles. Keys: buildings, landuse,
            railways, parking, traffic_signals, street_furniture, cycling,
            utilities. If None, only highways are queried.

    Returns:
        Overpass QL query string
    """
    # Overpass poly filter uses "lat lon" space-separated pairs
    poly_str = " ".join(f"{lat} {lng}" for lng, lat in polygon_coords)
    el = enabled_layers or {}

    fragments = []
    # Roads are always queried
    fragments.append(f'way["highway"](poly:"{poly_str}");')

    if el.get("buildings"):
        fragments.append(f'way["building"](poly:"{poly_str}");')

    if el.get("landuse"):
        fragments.append(f'way["leisure"="park"](poly:"{poly_str}");')
        fragments.append(f'way["natural"="water"](poly:"{poly_str}");')
        fragments.append(f'way["waterway"="riverbank"](poly:"{poly_str}");')
        fragments.append(f'way["landuse"~"industrial|commercial|residential"](poly:"{poly_str}");')

    if el.get("railways"):
        fragments.append(f'way["railway"~"rail|tram|light_rail|subway"](poly:"{poly_str}");')

    if el.get("parking"):
        fragments.append(f'way["amenity"="parking"](poly:"{poly_str}");')
        fragments.append(f'node["amenity"="parking_space"](poly:"{poly_str}");')

    if el.get("traffic_signals"):
        fragments.append(f'node["highway"="traffic_signals"](poly:"{poly_str}");')

    if el.get("street_furniture"):
        fragments.append(f'node["natural"="tree"](poly:"{poly_str}");')
        fragments.append(f'node["amenity"="bench"](poly:"{poly_str}");')
        fragments.append(f'node["highway"="street_lamp"](poly:"{poly_str}");')

    if el.get("cycling"):
        fragments.append(f'way["highway"="cycleway"](poly:"{poly_str}");')

    if el.get("utilities"):
        fragments.append(f'node["man_made"="manhole"](poly:"{poly_str}");')
        fragments.append(f'way["power"~"line|minor_line"](poly:"{poly_str}");')

    inner = "".join(fragments)
    return (
        f'[out:json][timeout:{timeout}];'
        f'({inner});'
        f'(._;>;);out body;'
    )


def query_overpass(
    polygon_coords: list[list[float]],
    overpass_url: str = "https://overpass-api.de/api/interpreter",
    timeout: int = 60,
    cache_dir: str | None = None,
    cache_ttl: int = 3600,
    enabled_layers: dict[str, bool] | None = None,
) -> dict[str, list[dict]]:
    """Query Overpass API for features within a polygon.

    Returns dict with keys:
        "ways": list of {id, nodes: [{lat, lon}], tags: {}} dicts
        "nodes": list of {id, lat, lon, tags: {}} dicts (point features)
    """
    # Check cache first
    key = _cache_key(polygon_coords, enabled_layers)
    if cache_dir:
        cached = _read_cache(cache_dir, key, cache_ttl)
        if cached is not None:
            return cached

    query = build_overpass_query(polygon_coords, timeout, enabled_layers)
    start = time.time()

    for attempt in range(2):
        try:
            resp = requests.post(
                overpass_url,
                data={"data": query},
                timeout=timeout + 10,
            )

            if resp.status_code == 429:
                if attempt == 0:
                    logger.warning("Overpass rate limited, waiting 10s before retry")
                    time.sleep(10)
                    continue
                raise OverpassError(
                    "Overpass API rate limited",
                    code="OVERPASS_RATE_LIMITED",
                    status_code=429,
                )

            if resp.status_code in (500, 503):
                if attempt == 0:
                    logger.warning(f"Overpass returned {resp.status_code}, retrying with 2x timeout")
                    timeout *= 2
                    query = build_overpass_query(polygon_coords, timeout, enabled_layers)
                    continue
                raise OverpassError(
                    f"Overpass server error ({resp.status_code})",
                    code="OVERPASS_UNAVAILABLE",
                    status_code=502,
                )

            resp.raise_for_status()
            break

        except requests.Timeout:
            if attempt == 0:
                logger.warning("Overpass timeout, retrying with 2x timeout")
                timeout *= 2
                query = build_overpass_query(polygon_coords, timeout, enabled_layers)
                continue
            raise OverpassError("Overpass API timed out", code="OVERPASS_TIMEOUT", status_code=504)

        except requests.RequestException as e:
            raise OverpassError(f"Overpass request failed: {e}", code="OVERPASS_ERROR", status_code=502)

    elapsed = time.time() - start
    data = resp.json()

    elements = data.get("elements", [])
    nodes_by_id: dict[int, dict] = {}
    raw_ways: list[dict] = []
    feature_nodes: list[dict] = []

    for el in elements:
        try:
            if el.get("type") == "node" and "lat" in el and "lon" in el:
                nodes_by_id[el["id"]] = {"lat": el["lat"], "lon": el["lon"]}
                # Keep tagged nodes as point features
                if el.get("tags"):
                    feature_nodes.append({
                        "id": el["id"],
                        "lat": el["lat"],
                        "lon": el["lon"],
                        "tags": el["tags"],
                    })
            elif el.get("type") == "way":
                raw_ways.append(el)
        except (KeyError, TypeError):
            logger.warning(f"Skipping malformed element: {el}")
            continue

    # Resolve way node coordinates
    ways = []
    for way in raw_ways:
        tags = way.get("tags", {})
        if not tags:
            continue

        way_nodes = []
        for node_id in way.get("nodes", []):
            if node_id in nodes_by_id:
                way_nodes.append(nodes_by_id[node_id])

        if len(way_nodes) >= 2:
            ways.append({
                "id": way["id"],
                "nodes": way_nodes,
                "tags": tags,
            })

    result = {"ways": ways, "nodes": feature_nodes}

    logger.info(
        f"Overpass query returned {len(ways)} ways, {len(feature_nodes)} tagged nodes, "
        f"{len(nodes_by_id)} total nodes in {elapsed:.2f}s"
    )

    # Cache the result
    if cache_dir and (ways or feature_nodes):
        _write_cache(cache_dir, key, result)

    return result
