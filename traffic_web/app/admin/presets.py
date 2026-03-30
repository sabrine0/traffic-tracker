from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth.deps import get_db, require_staff
from ..db.models import ConfigPreset, User
from ..services.audit import log_event


router = APIRouter(prefix="/presets", tags=["admin-presets"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _parse_json(text: str) -> tuple[bool, dict]:
    if not text.strip():
        return True, {}
    try:
        data = json.loads(text)
        return True, data if isinstance(data, dict) else {}
    except Exception:
        return False, {}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def presets_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    query = db.query(ConfigPreset).order_by(ConfigPreset.created_at.desc())
    if user.role != "admin":
        query = query.filter(ConfigPreset.created_by == user.id)
    presets = query.all()
    return templates.TemplateResponse(
        "admin/presets_list.html",
        {"request": request, "user": user, "presets": presets},
    )


@router.get("/new", response_class=HTMLResponse)
def presets_new(request: Request, user: User = Depends(require_staff)):
    return templates.TemplateResponse(
        "admin/presets_form.html",
        {"request": request, "user": user, "is_new": True, "form": {"config_json": "{}", "is_active": "on"}},
    )


@router.post("/new", response_class=HTMLResponse)
def presets_create(
    request: Request,
    name: str = Form(...),
    config_json: str = Form("{}"),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    name = name.strip()
    form = {
        "name": name,
        "config_json": config_json,
        "is_active": is_active,
    }
    if db.query(ConfigPreset).filter(ConfigPreset.name == name).first():
        return templates.TemplateResponse(
            "admin/presets_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Name already exists.", "form": form},
            status_code=400,
        )
    ok, cfg = _parse_json(config_json)
    if not ok:
        return templates.TemplateResponse(
            "admin/presets_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "config_json must be valid JSON object.", "form": form},
            status_code=400,
        )
    preset = ConfigPreset(
        name=name,
        config_json=json.dumps(cfg),
        created_by=admin.id,
        is_active=is_active == "on",
    )
    db.add(preset)
    db.commit()
    log_event(
        db,
        action="config_preset_created",
        actor_user_id=admin.id,
        target_type="config_preset",
        target_id=str(preset.id),
        details={"name": name},
    )
    return RedirectResponse(url="/admin/presets", status_code=303)


@router.get("/{preset_id}/edit", response_class=HTMLResponse)
def presets_edit(
    request: Request,
    preset_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    preset = db.query(ConfigPreset).filter(ConfigPreset.id == preset_id).first()
    if not preset:
        return HTMLResponse("Preset not found", status_code=404)
    if admin.role != "admin" and preset.created_by != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    form = {
        "name": preset.name,
        "config_json": preset.config_json or "{}",
        "is_active": "on" if preset.is_active else None,
    }
    return templates.TemplateResponse(
        "admin/presets_form.html",
        {"request": request, "user": admin, "is_new": False, "preset": preset, "form": form},
    )


@router.post("/{preset_id}/edit", response_class=HTMLResponse)
def presets_update(
    request: Request,
    preset_id: int,
    name: str = Form(...),
    config_json: str = Form("{}"),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    preset = db.query(ConfigPreset).filter(ConfigPreset.id == preset_id).first()
    if not preset:
        return HTMLResponse("Preset not found", status_code=404)
    if admin.role != "admin" and preset.created_by != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    name = name.strip()
    form = {
        "name": name,
        "config_json": config_json,
        "is_active": is_active,
    }
    other = db.query(ConfigPreset).filter(ConfigPreset.name == name, ConfigPreset.id != preset_id).first()
    if other:
        return templates.TemplateResponse(
            "admin/presets_form.html",
            {"request": request, "user": admin, "is_new": False, "preset": preset, "error": "Name already exists.", "form": form},
            status_code=400,
        )
    ok, cfg = _parse_json(config_json)
    if not ok:
        return templates.TemplateResponse(
            "admin/presets_form.html",
            {"request": request, "user": admin, "is_new": False, "preset": preset, "error": "config_json must be valid JSON object.", "form": form},
            status_code=400,
        )
    preset.name = name
    preset.config_json = json.dumps(cfg)
    preset.is_active = is_active == "on"
    db.add(preset)
    db.commit()
    log_event(
        db,
        action="config_preset_updated",
        actor_user_id=admin.id,
        target_type="config_preset",
        target_id=str(preset.id),
        details={"name": name},
    )
    return RedirectResponse(url="/admin/presets", status_code=303)


@router.post("/{preset_id}/delete")
def presets_delete(
    preset_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    preset = db.query(ConfigPreset).filter(ConfigPreset.id == preset_id).first()
    if not preset:
        return HTMLResponse("Preset not found", status_code=404)
    if admin.role != "admin" and preset.created_by != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    name = preset.name
    db.delete(preset)
    db.commit()
    log_event(
        db,
        action="config_preset_deleted",
        actor_user_id=admin.id,
        target_type="config_preset",
        target_id=str(preset_id),
        details={"name": name},
    )
    return RedirectResponse(url="/admin/presets", status_code=303)
