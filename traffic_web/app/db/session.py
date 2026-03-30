from __future__ import annotations

from pathlib import Path
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _default_db_url() -> str:
    base_dir = Path(__file__).resolve().parents[1]
    data_dir = base_dir / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "traffic.db"
    return f"sqlite:///{db_path.as_posix()}"


DB_URL = os.getenv("TRAFFIC_TRACKER_DB_URL", _default_db_url())
_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()
