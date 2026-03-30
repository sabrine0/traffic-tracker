from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db.models import LoginAttempt


def log_attempt(db: Session, username: str, ip: str, success: bool) -> None:
    attempt = LoginAttempt(username=username, ip=ip, success=success)
    db.add(attempt)
    db.commit()


def is_rate_limited(
    db: Session,
    username: str,
    ip: str,
    window_seconds: int = 900,
    max_attempts: int = 5,
) -> bool:
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    q = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.created_at >= cutoff)
        .filter(LoginAttempt.success == False)  # noqa: E712
        .filter((LoginAttempt.username == username) | (LoginAttempt.ip == ip))
    )
    return q.count() >= max_attempts
