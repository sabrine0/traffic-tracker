import os

ROAD_WIDTH_DEFAULTS = {
    "motorway":    {"classification": "main",      "lanes": 3, "lane_width": 3.50, "width": 10.50, "sidewalk": "no",   "divided": True},
    "trunk":       {"classification": "main",      "lanes": 2, "lane_width": 3.50, "width":  7.00, "sidewalk": "no",   "divided": True},
    "primary":     {"classification": "main",      "lanes": 2, "lane_width": 3.25, "width":  6.50, "sidewalk": "both", "divided": False},
    "secondary":   {"classification": "secondary", "lanes": 2, "lane_width": 3.25, "width":  6.50, "sidewalk": "both", "divided": False},
    "tertiary":    {"classification": "secondary", "lanes": 2, "lane_width": 3.00, "width":  6.00, "sidewalk": "both", "divided": False},
    "residential": {"classification": "local",     "lanes": 2, "lane_width": 3.00, "width":  6.00, "sidewalk": "both", "divided": False},
    "service":     {"classification": "local",     "lanes": 1, "lane_width": 3.00, "width":  3.00, "sidewalk": "no",   "divided": False},
    "track":       {"classification": "local",     "lanes": 1, "lane_width": 3.00, "width":  3.00, "sidewalk": "no",   "divided": False},
}

# Fallback for unknown highway types
DEFAULT_ROAD = {"classification": "local", "lanes": 2, "lane_width": 3.00, "width": 6.00, "sidewalk": "both", "divided": False}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    OVERPASS_API_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    OVERPASS_TIMEOUT = int(os.environ.get("OVERPASS_TIMEOUT", "60"))
    MAX_EXPORT_AREA_KM2 = float(os.environ.get("MAX_AREA_KM2", "25"))
    TEMP_DIR = os.environ.get("TEMP_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "output"))
    ROAD_WIDTH_DEFAULTS = ROAD_WIDTH_DEFAULTS
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MB max request body
    CACHE_ENABLED = os.environ.get("CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
    CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache"))
    CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))
    CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://localhost:5173")


class DevelopmentConfig(Config):
    DEBUG = True
    CORS_ORIGIN = "*"


class TestingConfig(Config):
    TESTING = True
    OVERPASS_TIMEOUT = 10
    CACHE_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
