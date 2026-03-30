from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth.deps import get_db, require_admin, require_staff
from ..auth.passwords import hash_password
from ..db.models import User
from ..services.audit import log_event


router = APIRouter(prefix="/users", tags=["admin-users"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def users_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/users_list.html",
        {"request": request, "user": user, "users": users},
    )


@router.get("/new", response_class=HTMLResponse)
def user_new(request: Request, user: User = Depends(require_staff)):
    return templates.TemplateResponse(
        "admin/users_form.html",
        {"request": request, "user": user, "is_new": True, "form": {"is_active": "on"}},
    )


@router.post("/new", response_class=HTMLResponse)
def user_create(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(""),
    role: str = Form("viewer"),
    password: str = Form(...),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    email = email.strip().lower()
    username = username.strip()
    form = {
        "email": email,
        "username": username,
        "full_name": full_name,
        "role": role,
        "is_active": is_active,
    }
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "admin/users_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Email already exists.", "form": form},
            status_code=400,
        )
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(
            "admin/users_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Username already exists.", "form": form},
            status_code=400,
        )
    allowed_roles = ("admin", "user", "viewer")
    if admin.role != "admin":
        if role not in ("user", "viewer"):
            role = "viewer"
    else:
        if role not in allowed_roles:
            role = "viewer"
    new_user = User(
        email=email,
        username=username,
        full_name=full_name.strip(),
        role=role,
        is_active=is_active == "on",
        password_hash=hash_password(password),
    )
    db.add(new_user)
    db.commit()
    log_event(
        db,
        action="user_created",
        actor_user_id=admin.id,
        target_type="user",
        target_id=str(new_user.id),
        details={"email": email, "username": username, "role": new_user.role},
    )
    redirect_url = "/admin/users" if admin.role == "admin" else "/admin"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/{user_id}/edit", response_class=HTMLResponse)
def user_edit(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return HTMLResponse("User not found", status_code=404)
    form = {
        "email": target.email,
        "username": target.username,
        "full_name": target.full_name or "",
        "role": target.role,
        "is_active": "on" if target.is_active else None,
    }
    return templates.TemplateResponse(
        "admin/users_form.html",
        {"request": request, "user": admin, "is_new": False, "target": target, "form": form},
    )


@router.post("/{user_id}/edit", response_class=HTMLResponse)
def user_update(
    request: Request,
    user_id: int,
    email: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(""),
    role: str = Form("viewer"),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return HTMLResponse("User not found", status_code=404)
    email = email.strip().lower()
    username = username.strip()
    form = {
        "email": email,
        "username": username,
        "full_name": full_name,
        "role": role,
        "is_active": is_active,
    }
    email_owner = db.query(User).filter(User.email == email, User.id != user_id).first()
    if email_owner:
        return templates.TemplateResponse(
            "admin/users_form.html",
            {"request": request, "user": admin, "is_new": False, "target": target, "error": "Email already exists.", "form": form},
            status_code=400,
        )
    user_owner = db.query(User).filter(User.username == username, User.id != user_id).first()
    if user_owner:
        return templates.TemplateResponse(
            "admin/users_form.html",
            {"request": request, "user": admin, "is_new": False, "target": target, "error": "Username already exists.", "form": form},
            status_code=400,
        )
    target.email = email
    target.username = username
    target.full_name = full_name.strip()
    target.role = role if role in ("admin", "user", "viewer") else "viewer"
    target.is_active = is_active == "on"
    db.add(target)
    db.commit()
    log_event(
        db,
        action="user_updated",
        actor_user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        details={"email": email, "username": username, "role": target.role, "is_active": target.is_active},
    )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/disable")
def user_disable(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return HTMLResponse("User not found", status_code=404)
    target.is_active = False
    db.add(target)
    db.commit()
    log_event(
        db,
        action="user_disabled",
        actor_user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        details={"email": target.email},
    )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/reset_password")
def user_reset_password(
    user_id: int,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return HTMLResponse("User not found", status_code=404)
    target.password_hash = hash_password(new_password)
    db.add(target)
    db.commit()
    log_event(
        db,
        action="user_password_reset",
        actor_user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        details={"email": target.email},
    )
    return RedirectResponse(url=f"/admin/users/{user_id}/edit", status_code=303)
