from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..db.models import Run


def _to_json(data: Any) -> str | None:
    if data is None:
        return None
    try:
        return json.dumps(data)
    except Exception:
        return None


def get_run_by_job_id(db: Session, job_id: str) -> Optional[Run]:
    return db.query(Run).filter(Run.job_id == job_id).first()


def create_run(
    db: Session,
    job_id: str,
    video_filename: str,
    title: str,
    place: str,
    recorded_at: datetime | None = None,
    owner_user_id: int | None = None,
    status: str = "uploaded",
) -> Run:
    existing = get_run_by_job_id(db, job_id)
    if existing:
        return existing
    run = Run(
        job_id=job_id,
        video_filename=video_filename,
        title=title,
        place=place,
        recorded_at=recorded_at,
        owner_user_id=owner_user_id,
        status=status,
    )
    db.add(run)
    db.commit()
    return run


def update_run(
    db: Session,
    job_id: str,
    status: Optional[str] = None,
    title: Optional[str] = None,
    place: Optional[str] = None,
    recorded_at: datetime | None = None,
    metrics: Any | None = None,
    outputs: Any | None = None,
    config: Any | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    run = get_run_by_job_id(db, job_id)
    if not run:
        return
    if status is not None:
        run.status = status
    if title is not None:
        run.title = title
    if place is not None:
        run.place = place
    if recorded_at is not None:
        run.recorded_at = recorded_at
    if metrics is not None:
        run.metrics_json = _to_json(metrics)
    if outputs is not None:
        run.outputs_json = _to_json(outputs)
    if config is not None:
        run.config_json = _to_json(config)
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at
    db.add(run)
    db.commit()
