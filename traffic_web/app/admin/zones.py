from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth.deps import get_db, require_staff
from ..db.models import User, ZoneTemplate
from ..services.audit import log_event


router = APIRouter(prefix="/zones", tags=["admin-zones"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _parse_json(text: str, default: dict | list) -> tuple[bool, dict | list]:
    if not text.strip():
        return True, default
    try:
        data = json.loads(text)
        return True, data
    except Exception:
        return False, default


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def zones_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    query = db.query(ZoneTemplate).order_by(ZoneTemplate.created_at.desc())
    if user.role != "admin":
        query = query.filter(ZoneTemplate.created_by == user.id)
    templates_list = query.all()
    return templates.TemplateResponse(
        "admin/zones_list.html",
        {"request": request, "user": user, "templates": templates_list},
    )


@router.get("/new", response_class=HTMLResponse)
def zones_new(request: Request, user: User = Depends(require_staff)):
    return templates.TemplateResponse(
        "admin/zones_form.html",
        {
            "request": request,
            "user": user,
            "is_new": True,
            "form": {"labels_json": "[]", "zones_json": "{\"entry\": {}, \"exit\": {}}", "is_active": "on"},
        },
    )


@router.post("/new", response_class=HTMLResponse)
def zones_create(
    request: Request,
    name: str = Form(...),
    labels_json: str = Form("[]"),
    zones_json: str = Form("{\"entry\": {}, \"exit\": {}}"),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    name = name.strip()
    form = {
        "name": name,
        "labels_json": labels_json,
        "zones_json": zones_json,
        "is_active": is_active,
    }
    if db.query(ZoneTemplate).filter(ZoneTemplate.name == name).first():
        return templates.TemplateResponse(
            "admin/zones_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Name already exists.", "form": form},
            status_code=400,
        )
    ok_labels, labels = _parse_json(labels_json, [])
    ok_zones, zones = _parse_json(zones_json, {"entry": {}, "exit": {}})
    if not ok_labels or not isinstance(labels, list):
        return templates.TemplateResponse(
            "admin/zones_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "labels_json must be valid JSON list.", "form": form},
            status_code=400,
        )
    if not ok_zones or not isinstance(zones, dict):
        return templates.TemplateResponse(
            "admin/zones_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "zones_json must be valid JSON object.", "form": form},
            status_code=400,
        )
    template = ZoneTemplate(
        name=name,
        labels_json=json.dumps(labels),
        zones_json=json.dumps(zones),
        created_by=admin.id,
        is_active=is_active == "on",
    )
    db.add(template)
    db.commit()
    log_event(
        db,
        action="zone_template_created",
        actor_user_id=admin.id,
        target_type="zone_template",
        target_id=str(template.id),
        details={"name": name},
    )
    return RedirectResponse(url="/admin/zones", status_code=303)


@router.get("/{template_id}/edit", response_class=HTMLResponse)
def zones_edit(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    template = db.query(ZoneTemplate).filter(ZoneTemplate.id == template_id).first()
    if not template:
        return HTMLResponse("Template not found", status_code=404)
    if admin.role != "admin" and template.created_by != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    form = {
        "name": template.name,
        "labels_json": template.labels_json or "[]",
        "zones_json": template.zones_json or "{\"entry\": {}, \"exit\": {}}",
        "is_active": "on" if template.is_active else None,
    }
    return templates.TemplateResponse(
        "admin/zones_form.html",
        {"request": request, "user": admin, "is_new": False, "template": template, "form": form},
    )


@router.post("/{template_id}/edit", response_class=HTMLResponse)
def zones_update(
    request: Request,
    template_id: int,
    name: str = Form(...),
    labels_json: str = Form("[]"),
    zones_json: str = Form("{\"entry\": {}, \"exit\": {}}"),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    template = db.query(ZoneTemplate).filter(ZoneTemplate.id == template_id).first()
    if not template:
        return HTMLResponse("Template not found", status_code=404)
    if admin.role != "admin" and template.created_by != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    name = name.strip()
    form = {
        "name": name,
        "labels_json": labels_json,
        "zones_json": zones_json,
        "is_active": is_active,
    }
    other = db.query(ZoneTemplate).filter(ZoneTemplate.name == name, ZoneTemplate.id != template_id).first()
    if other:
        return templates.TemplateResponse(
            "admin/zones_form.html",
            {"request": request, "user": admin, "is_new": False, "template": template, "error": "Name already exists.", "form": form},
            status_code=400,
        )
    ok_labels, labels = _parse_json(labels_json, [])
    ok_zones, zones = _parse_json(zones_json, {"entry": {}, "exit": {}})
    if not ok_labels or not isinstance(labels, list):
        return templates.TemplateResponse(
            "admin/zones_form.html",
            {"request": request, "user": admin, "is_new": False, "template": template, "error": "labels_json must be valid JSON list.", "form": form},
            status_code=400,
        )
    if not ok_zones or not isinstance(zones, dict):
        return templates.TemplateResponse(
            "admin/zones_form.html",
            {"request": request, "user": admin, "is_new": False, "template": template, "error": "zones_json must be valid JSON object.", "form": form},
            status_code=400,
        )
    template.name = name
    template.labels_json = json.dumps(labels)
    template.zones_json = json.dumps(zones)
    template.is_active = is_active == "on"
    db.add(template)
    db.commit()
    log_event(
        db,
        action="zone_template_updated",
        actor_user_id=admin.id,
        target_type="zone_template",
        target_id=str(template.id),
        details={"name": name},
    )
    return RedirectResponse(url="/admin/zones", status_code=303)


@router.post("/{template_id}/delete")
def zones_delete(
    template_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    template = db.query(ZoneTemplate).filter(ZoneTemplate.id == template_id).first()
    if not template:
        return HTMLResponse("Template not found", status_code=404)
    if admin.role != "admin" and template.created_by != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    name = template.name
    db.delete(template)
    db.commit()
    log_event(
        db,
        action="zone_template_deleted",
        actor_user_id=admin.id,
        target_type="zone_template",
        target_id=str(template_id),
        details={"name": name},
    )
    return RedirectResponse(url="/admin/zones", status_code=303)
