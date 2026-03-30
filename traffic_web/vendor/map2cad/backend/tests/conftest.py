import pytest
from app import create_app


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "MAX_EXPORT_AREA_KM2": 25, "CACHE_ENABLED": False})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


VALID_POLYGON = [
    [-73.99, 40.75],
    [-73.98, 40.75],
    [-73.98, 40.76],
    [-73.99, 40.76],
]

LARGE_POLYGON = [
    [-74.5, 40.0],
    [-73.5, 40.0],
    [-73.5, 41.0],
    [-74.5, 41.0],
]
