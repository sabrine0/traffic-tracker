from __future__ import annotations

from pathlib import Path
import logging


logger = logging.getLogger(__name__)


def _find_alembic_ini(start: Path) -> Path:
    for parent in start.resolve().parents:
        candidate = parent / "alembic.ini"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("alembic.ini not found")


def init_db() -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        message = (
            "Alembic is required to initialize the database. "
            "Install it with `pip install alembic`."
        )
        logger.error(message)
        raise RuntimeError(message) from exc

    alembic_ini = _find_alembic_ini(Path(__file__).resolve())
    cfg = Config(str(alembic_ini))
    script_dir = alembic_ini.parent / "traffic_web" / "app" / "db" / "alembic"
    if script_dir.is_dir():
        cfg.set_main_option("script_location", str(script_dir.resolve()))
    command.upgrade(cfg, "head")
