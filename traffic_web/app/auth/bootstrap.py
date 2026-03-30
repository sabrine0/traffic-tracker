from __future__ import annotations

import logging
import os

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db.models import User
from .passwords import hash_password


logger = logging.getLogger(__name__)


def _normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def _normalize_username(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()


def ensure_admin_user(db: Session) -> None:
    email = _normalize_email(os.getenv("TRAFFIC_TRACKER_ADMIN_EMAIL"))
    password = os.getenv("TRAFFIC_TRACKER_ADMIN_PASSWORD")
    username = _normalize_username(os.getenv("TRAFFIC_TRACKER_ADMIN_USERNAME", "admin"))
    if not email or not password:
        logger.info("Admin bootstrap skipped: missing TRAFFIC_TRACKER_ADMIN_EMAIL or TRAFFIC_TRACKER_ADMIN_PASSWORD.")
        return

    active_admin = (
        db.query(User)
        .filter(User.role == "admin", User.is_active == True)  # noqa: E712
        .first()
    )
    if active_admin:
        logger.info("Active admin already exists; skipping bootstrap.")
        return

    user_by_email = db.query(User).filter(User.email == email).first()
    if user_by_email:
        if username and username != user_by_email.username:
            conflict = db.query(User).filter(User.username == username, User.id != user_by_email.id).first()
            if conflict:
                logger.error(
                    "Admin bootstrap aborted: username '%s' already in use by user id %s.",
                    username,
                    conflict.id,
                )
                return
        user_by_email.password_hash = hash_password(password)
        user_by_email.role = "admin"
        user_by_email.is_active = True
        user_by_email.full_name = user_by_email.full_name or "Admin"
        if username and username != user_by_email.username:
            user_by_email.username = username
        try:
            db.add(user_by_email)
            db.commit()
            logger.info("Admin bootstrap updated user by email: %s.", email)
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Admin bootstrap failed while updating user by email.")
        return

    user_by_username = db.query(User).filter(User.username == username).first()
    if user_by_username:
        if email and email != user_by_username.email:
            conflict = db.query(User).filter(User.email == email, User.id != user_by_username.id).first()
            if conflict:
                logger.error(
                    "Admin bootstrap aborted: email '%s' already in use by user id %s.",
                    email,
                    conflict.id,
                )
                return
        user_by_username.password_hash = hash_password(password)
        user_by_username.role = "admin"
        user_by_username.is_active = True
        user_by_username.full_name = user_by_username.full_name or "Admin"
        if email and email != user_by_username.email:
            user_by_username.email = email
        try:
            db.add(user_by_username)
            db.commit()
            logger.info("Admin bootstrap updated user by username: %s.", username)
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Admin bootstrap failed while updating user by username.")
        return

    if db.query(User).filter(User.email == email).first():
        logger.error("Admin bootstrap aborted: email '%s' already exists.", email)
        return
    if username and db.query(User).filter(User.username == username).first():
        logger.error("Admin bootstrap aborted: username '%s' already exists.", username)
        return

    admin = User(
        email=email,
        username=username or "admin",
        full_name="Admin",
        password_hash=hash_password(password),
        role="admin",
        is_active=True,
    )
    try:
        db.add(admin)
        db.commit()
        logger.info("Admin bootstrap created new admin: %s.", email)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Admin bootstrap failed while creating admin user.")
