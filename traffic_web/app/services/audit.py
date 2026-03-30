from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..db.models import AuditLog


def log_event(
    db: Session,
    action: str,
    actor_user_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> None:
    details_json = json.dumps(details or {}) if details is not None else None
    event = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details_json=details_json,
        ip=ip,
    )
    db.add(event)
    db.commit()
