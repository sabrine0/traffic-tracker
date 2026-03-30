from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import User, UserSession


SESSION_COOKIE_NAME = "tt_session"
DEFAULT_SESSION_TTL_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    db: Session,
    user: User,
    ip: str | None,
    user_agent: str | None,
    ttl_days: int = DEFAULT_SESSION_TTL_DAYS,
) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = datetime.utcnow()
    expires_at = now + timedelta(days=ttl_days)
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(session)
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    token_hash = _hash_token(token)
    session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
    if session and session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        db.add(session)
        db.commit()


def get_user_by_session(db: Session, token: str) -> Optional[User]:
    if not token:
        return None
    token_hash = _hash_token(token)
    session = (
        db.query(UserSession)
        .filter(UserSession.token_hash == token_hash)
        .first()
    )
    if not session:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= datetime.utcnow():
        return None
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        return None
    return user
