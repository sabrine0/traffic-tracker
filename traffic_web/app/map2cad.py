from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parent
MAP2CAD_VENDOR_DIR = APP_DIR.parent / "vendor" / "map2cad"
MAP2CAD_BACKEND_DIR = MAP2CAD_VENDOR_DIR / "backend"
MAP2CAD_DATA_DIR = APP_DIR / "_data" / "map2cad"
MAP2CAD_OUTPUT_DIR = MAP2CAD_DATA_DIR / "output"
MAP2CAD_CACHE_DIR = MAP2CAD_DATA_DIR / "cache"
MAP2CAD_STATIC_DIR = APP_DIR / "static" / "map2cad"


def _ensure_vendor_backend_on_path() -> None:
    backend_dir = str(MAP2CAD_BACKEND_DIR.resolve())
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


@lru_cache(maxsize=1)
def create_map2cad_wsgi_app():
    _ensure_vendor_backend_on_path()

    MAP2CAD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MAP2CAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    from app import create_app  # type: ignore

    return create_app(
        {
            "TEMP_DIR": str(MAP2CAD_OUTPUT_DIR),
            "CACHE_DIR": str(MAP2CAD_CACHE_DIR),
            "CORS_ORIGIN": "*",
        }
    )


def get_map2cad_index_path() -> Path | None:
    index_path = MAP2CAD_STATIC_DIR / "index.html"
    return index_path if index_path.is_file() else None
