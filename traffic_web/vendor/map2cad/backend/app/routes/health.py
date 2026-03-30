import logging
import requests
from flask import Blueprint, jsonify, current_app

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health")
def health_check():
    """Enhanced health check — reports status of all components."""
    components = {}

    # App status
    components["app"] = "ok"

    # Overpass API reachability
    try:
        overpass_url = current_app.config.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
        resp = requests.get(overpass_url, timeout=5)
        components["overpass"] = "ok" if resp.status_code < 500 else "degraded"
    except Exception:
        components["overpass"] = "unreachable"

    # Overall status
    if all(v == "ok" for v in components.values()):
        overall = "healthy"
    elif components["app"] == "ok":
        overall = "degraded"
    else:
        overall = "unhealthy"

    return jsonify({
        "status": overall,
        "components": components,
    })
