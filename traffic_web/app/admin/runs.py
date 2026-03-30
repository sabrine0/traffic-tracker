from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_

from ..auth.deps import get_db, require_staff
from ..db.models import Camera, Project, Run, User
from ..services.audit import log_event


router = APIRouter(prefix="/runs", tags=["admin-runs"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
STATUS_OPTIONS = ["uploaded", "processing", "done", "failed"]


def _safe_json(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_json(text: str | None) -> tuple[bool, dict | None]:
    if text is None or not text.strip():
        return True, None
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return False, None
        return True, data
    except Exception:
        return False, None


def _parse_datetime(value: str | None) -> tuple[bool, datetime | None]:
    if value is None or not value.strip():
        return True, None
    try:
        return True, datetime.fromisoformat(value.strip())
    except Exception:
        return False, None


def _parse_int(value: str | None) -> tuple[bool, int | None]:
    if value is None or not str(value).strip():
        return True, None
    try:
        return True, int(value)
    except Exception:
        return False, None


def _parse_date_filter(value: str | None, end_of_day: bool = False) -> tuple[bool, datetime | None]:
    if value is None or not str(value).strip():
        return True, None
    text = value.strip()
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return False, None
    if end_of_day and ("T" not in text and " " not in text):
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return True, dt


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _class_label(key: str) -> str:
    mapping = {
        "person": "Person",
        "bicycle": "Bicycle",
        "car": "Car",
        "motorcycle": "Motorcycle",
        "bus": "Bus",
        "truck": "Truck",
    }
    return mapping.get(key, key.replace("_", " ").title())


def _collect_zone_names(entry_counts: dict, exit_counts: dict, od_counts: dict) -> list[str]:
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names:
            names.append(name)

    for k in entry_counts.keys():
        add(str(k))
    for k in exit_counts.keys():
        add(str(k))
    for k in od_counts.keys():
        if "->" in k:
            a, b = k.split("->", 1)
            add(a)
            add(b)

    return names


def _build_class_rows(class_counts: dict, classes_used: list | None) -> list[dict]:
    counts = {str(k): _int(v) for k, v in (class_counts or {}).items()}
    if classes_used:
        keys = [str(k) for k in classes_used]
    else:
        keys = list(counts.keys())
    rows: list[dict] = []
    for key in keys:
        rows.append({"label": _class_label(key), "count": counts.get(key, 0)})
    for key, count in counts.items():
        if key in keys:
            continue
        rows.append({"label": _class_label(key), "count": count})
    return rows


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def runs_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    q: str | None = Query(None),
    user_q: str | None = Query(None, alias="user"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    query = db.query(Run)
    error = None
    q = (q or "").strip()
    user_q = (user_q or "").strip()

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Run.job_id.ilike(pattern),
                Run.title.ilike(pattern),
                Run.place.ilike(pattern),
                Run.video_filename.ilike(pattern),
            )
        )

    if user.role != "admin":
        user_q = ""
        query = query.filter(Run.owner_user_id == user.id)
    if user_q:
        ok_id, user_id = _parse_int(user_q)
        if ok_id and user_id is not None:
            query = query.filter(Run.owner_user_id == user_id)
        else:
            pattern = f"%{user_q}%"
            query = query.join(User, User.id == Run.owner_user_id).filter(
                or_(
                    User.username.ilike(pattern),
                    User.email.ilike(pattern),
                    User.full_name.ilike(pattern),
                )
            )

    ok_from, date_from_dt = _parse_date_filter(date_from, end_of_day=False)
    ok_to, date_to_dt = _parse_date_filter(date_to, end_of_day=True)
    if not ok_from or not ok_to:
        error = "Date filters must be in YYYY-MM-DD or ISO datetime format."
    else:
        sort_key = func.coalesce(Run.recorded_at, Run.created_at)
        if date_from_dt:
            query = query.filter(sort_key >= date_from_dt)
        if date_to_dt:
            query = query.filter(sort_key <= date_to_dt)

    runs = (
        query.order_by(desc(func.coalesce(Run.recorded_at, Run.created_at)))
        .limit(200)
        .all()
    )
    owner_ids = {r.owner_user_id for r in runs if r.owner_user_id}
    owners = {}
    if owner_ids:
        users = db.query(User).filter(User.id.in_(owner_ids)).all()
        owners = {
            u.id: f"{u.username} ({u.email})" if u.email else u.username
            for u in users
        }
    return templates.TemplateResponse(
        "admin/runs_list.html",
        {
            "request": request,
            "user": user,
            "runs": runs,
            "owners": owners,
            "filters": {"q": q, "user": user_q, "date_from": date_from, "date_to": date_to},
            "error": error,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def run_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    if user.role == "admin":
        users = db.query(User).order_by(User.username.asc()).all()
    else:
        users = [user]
    form = {
        "job_id": "",
        "title": "",
        "place": "",
        "recorded_at": "",
        "status": "uploaded",
        "owner_user_id": str(user.id) if user.role != "admin" else "",
        "video_filename": "",
        "project_id": "",
        "camera_id": "",
        "started_at": "",
        "finished_at": "",
        "metrics_json": "{}",
        "outputs_json": "{}",
        "config_json": "{}",
    }
    return templates.TemplateResponse(
        "admin/runs_form.html",
        {"request": request, "user": user, "is_new": True, "form": form, "users": users, "status_options": STATUS_OPTIONS},
    )


@router.post("/new", response_class=HTMLResponse)
def run_create(
    request: Request,
    job_id: str = Form(...),
    title: str = Form(""),
    place: str = Form(""),
    recorded_at: str | None = Form(None),
    status: str = Form("uploaded"),
    owner_user_id: str | None = Form(None),
    video_filename: str = Form(""),
    project_id: str | None = Form(None),
    camera_id: str | None = Form(None),
    started_at: str | None = Form(None),
    finished_at: str | None = Form(None),
    metrics_json: str = Form("{}"),
    outputs_json: str = Form("{}"),
    config_json: str = Form("{}"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    job_id = job_id.strip()
    title = title.strip()
    place = place.strip()
    status = status.strip().lower()
    form = {
        "job_id": job_id,
        "title": title,
        "place": place,
        "recorded_at": recorded_at,
        "status": status,
        "owner_user_id": owner_user_id,
        "video_filename": video_filename,
        "project_id": project_id,
        "camera_id": camera_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "metrics_json": metrics_json,
        "outputs_json": outputs_json,
        "config_json": config_json,
    }

    if admin.role == "admin":
        users = db.query(User).order_by(User.username.asc()).all()
    else:
        users = [admin]
    if not job_id:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Video ID is required.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if not title:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Title is required.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if not place:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Place is required.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if status not in STATUS_OPTIONS:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Invalid status.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if db.query(Run).filter(Run.job_id == job_id).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Video ID already exists.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_owner, owner_id = _parse_int(owner_user_id)
    if not ok_owner:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Owner user ID must be an integer.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if admin.role != "admin":
        owner_id = admin.id
    if owner_id is not None and not db.query(User).filter(User.id == owner_id).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Owner user not found.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_project, project_id_val = _parse_int(project_id)
    if not ok_project:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Project ID must be an integer.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if project_id_val is not None and not db.query(Project).filter(Project.id == project_id_val).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Project not found.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_camera, camera_id_val = _parse_int(camera_id)
    if not ok_camera:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Camera ID must be an integer.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if camera_id_val is not None and not db.query(Camera).filter(Camera.id == camera_id_val).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Camera not found.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_recorded, recorded_at_dt = _parse_datetime(recorded_at)
    if not ok_recorded:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Recorded at must be ISO format.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_started, started_at_dt = _parse_datetime(started_at)
    if not ok_started:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Started at must be ISO format.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_finished, finished_at_dt = _parse_datetime(finished_at)
    if not ok_finished:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Finished at must be ISO format.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_metrics, metrics_obj = _parse_json(metrics_json)
    if not ok_metrics:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Metrics JSON must be a valid JSON object.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_outputs, outputs_obj = _parse_json(outputs_json)
    if not ok_outputs:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Outputs JSON must be a valid JSON object.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_config, config_obj = _parse_json(config_json)
    if not ok_config:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": True, "error": "Config JSON must be a valid JSON object.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    run = Run(
        job_id=job_id,
        title=title,
        place=place,
        recorded_at=recorded_at_dt,
        status=status,
        owner_user_id=owner_id,
        video_filename=video_filename.strip() or None,
        project_id=project_id_val,
        camera_id=camera_id_val,
        started_at=started_at_dt,
        finished_at=finished_at_dt,
        metrics_json=json.dumps(metrics_obj) if metrics_obj is not None else None,
        outputs_json=json.dumps(outputs_obj) if outputs_obj is not None else None,
        config_json=json.dumps(config_obj) if config_obj is not None else None,
    )
    db.add(run)
    db.commit()
    log_event(
        db,
        action="run_created",
        actor_user_id=admin.id,
        target_type="run",
        target_id=str(run.id),
        details={"job_id": job_id},
    )
    return RedirectResponse(url=f"/admin/runs/{run.id}", status_code=303)


@router.get("/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return HTMLResponse("Run not found", status_code=404)
    if user.role != "admin" and run.owner_user_id != user.id:
        return HTMLResponse("Not authorized", status_code=403)
    metrics = _safe_json(run.metrics_json)
    outputs = _safe_json(run.outputs_json)
    config = _safe_json(run.config_json)
    entry_counts = metrics.get("entry_counts") if isinstance(metrics.get("entry_counts"), dict) else {}
    exit_counts = metrics.get("exit_counts") if isinstance(metrics.get("exit_counts"), dict) else {}
    od_counts = metrics.get("od_counts") if isinstance(metrics.get("od_counts"), dict) else {}
    class_counts = metrics.get("class_counts") if isinstance(metrics.get("class_counts"), dict) else {}
    classes_used = metrics.get("classes") if isinstance(metrics.get("classes"), list) else []

    class_count_rows = _build_class_rows(class_counts, classes_used)
    zone_names = _collect_zone_names(entry_counts, exit_counts, od_counts)
    zone_rows = [
        {"zone": z, "entry": _int(entry_counts.get(z, 0)), "exit": _int(exit_counts.get(z, 0))}
        for z in zone_names
    ]
    od_rows = []
    for k, v in od_counts.items():
        if "->" not in k:
            continue
        entry, exit_ = k.split("->", 1)
        od_rows.append({"entry": entry, "exit": exit_, "count": _int(v)})
    od_rows.sort(key=lambda r: r["count"], reverse=True)
    od_matrix_rows = []
    for entry in zone_names:
        counts = [_int(od_counts.get(f"{entry}->{exit_}", 0)) for exit_ in zone_names]
        od_matrix_rows.append({"entry": entry, "counts": counts})
    od_matrix = {"cols": zone_names, "rows": od_matrix_rows}
    return templates.TemplateResponse(
        "admin/runs_detail.html",
        {
            "request": request,
            "user": user,
            "run": run,
            "metrics": metrics,
            "outputs": outputs,
            "config": config,
            "class_count_rows": class_count_rows,
            "zone_rows": zone_rows,
            "od_rows": od_rows,
            "od_matrix": od_matrix,
            "metrics_raw": run.metrics_json or "{}",
            "outputs_raw": run.outputs_json or "{}",
            "config_raw": run.config_json or "{}",
        },
    )


@router.get("/{run_id}/edit", response_class=HTMLResponse)
def run_edit(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return HTMLResponse("Run not found", status_code=404)
    if user.role != "admin" and run.owner_user_id != user.id:
        return HTMLResponse("Not authorized", status_code=403)
    if user.role == "admin":
        users = db.query(User).order_by(User.username.asc()).all()
    else:
        users = [user]
    form = {
        "job_id": run.job_id or "",
        "title": run.title or "",
        "place": run.place or "",
        "recorded_at": run.recorded_at.isoformat(sep=" ") if run.recorded_at else "",
        "status": run.status or "uploaded",
        "owner_user_id": run.owner_user_id or "",
        "video_filename": run.video_filename or "",
        "project_id": run.project_id or "",
        "camera_id": run.camera_id or "",
        "started_at": run.started_at.isoformat(sep=" ") if run.started_at else "",
        "finished_at": run.finished_at.isoformat(sep=" ") if run.finished_at else "",
        "metrics_json": run.metrics_json or "{}",
        "outputs_json": run.outputs_json or "{}",
        "config_json": run.config_json or "{}",
    }
    return templates.TemplateResponse(
        "admin/runs_form.html",
        {"request": request, "user": user, "is_new": False, "run": run, "form": form, "users": users, "status_options": STATUS_OPTIONS},
    )


@router.post("/{run_id}/edit", response_class=HTMLResponse)
def run_update(
    request: Request,
    run_id: int,
    job_id: str = Form(...),
    title: str = Form(""),
    place: str = Form(""),
    recorded_at: str | None = Form(None),
    status: str = Form("uploaded"),
    owner_user_id: str | None = Form(None),
    video_filename: str = Form(""),
    project_id: str | None = Form(None),
    camera_id: str | None = Form(None),
    started_at: str | None = Form(None),
    finished_at: str | None = Form(None),
    metrics_json: str = Form("{}"),
    outputs_json: str = Form("{}"),
    config_json: str = Form("{}"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return HTMLResponse("Run not found", status_code=404)
    if admin.role != "admin" and run.owner_user_id != admin.id:
        return HTMLResponse("Not authorized", status_code=403)

    job_id = job_id.strip()
    title = title.strip()
    place = place.strip()
    status = status.strip().lower()
    form = {
        "job_id": job_id,
        "title": title,
        "place": place,
        "recorded_at": recorded_at,
        "status": status,
        "owner_user_id": owner_user_id,
        "video_filename": video_filename,
        "project_id": project_id,
        "camera_id": camera_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "metrics_json": metrics_json,
        "outputs_json": outputs_json,
        "config_json": config_json,
    }
    if admin.role == "admin":
        users = db.query(User).order_by(User.username.asc()).all()
    else:
        users = [admin]

    if not job_id:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Video ID is required.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if job_id != run.job_id:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Video ID cannot be changed.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if status not in STATUS_OPTIONS:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Invalid status.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if not title:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Title is required.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if not place:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Place is required.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_owner, owner_id = _parse_int(owner_user_id)
    if not ok_owner:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Owner user ID must be an integer.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if admin.role != "admin":
        owner_id = admin.id
    if owner_id is not None and not db.query(User).filter(User.id == owner_id).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Owner user not found.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_project, project_id_val = _parse_int(project_id)
    if not ok_project:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Project ID must be an integer.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if project_id_val is not None and not db.query(Project).filter(Project.id == project_id_val).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Project not found.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_camera, camera_id_val = _parse_int(camera_id)
    if not ok_camera:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Camera ID must be an integer.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    if camera_id_val is not None and not db.query(Camera).filter(Camera.id == camera_id_val).first():
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Camera not found.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_recorded, recorded_at_dt = _parse_datetime(recorded_at)
    if not ok_recorded:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Recorded at must be ISO format.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_started, started_at_dt = _parse_datetime(started_at)
    if not ok_started:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Started at must be ISO format.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_finished, finished_at_dt = _parse_datetime(finished_at)
    if not ok_finished:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Finished at must be ISO format.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    ok_metrics, metrics_obj = _parse_json(metrics_json)
    if not ok_metrics:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Metrics JSON must be a valid JSON object.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_outputs, outputs_obj = _parse_json(outputs_json)
    if not ok_outputs:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Outputs JSON must be a valid JSON object.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )
    ok_config, config_obj = _parse_json(config_json)
    if not ok_config:
        return templates.TemplateResponse(
            "admin/runs_form.html",
            {"request": request, "user": admin, "is_new": False, "run": run, "error": "Config JSON must be a valid JSON object.", "form": form, "users": users, "status_options": STATUS_OPTIONS},
            status_code=400,
        )

    run.status = status
    run.title = title
    run.place = place
    run.recorded_at = recorded_at_dt
    run.owner_user_id = owner_id
    run.video_filename = video_filename.strip() or None
    run.project_id = project_id_val
    run.camera_id = camera_id_val
    run.started_at = started_at_dt
    run.finished_at = finished_at_dt
    run.metrics_json = json.dumps(metrics_obj) if metrics_obj is not None else None
    run.outputs_json = json.dumps(outputs_obj) if outputs_obj is not None else None
    run.config_json = json.dumps(config_obj) if config_obj is not None else None
    db.add(run)
    db.commit()
    log_event(
        db,
        action="run_updated",
        actor_user_id=admin.id,
        target_type="run",
        target_id=str(run.id),
        details={"job_id": job_id},
    )
    return RedirectResponse(url=f"/admin/runs/{run.id}", status_code=303)


@router.post("/{run_id}/delete")
def run_delete(
    run_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_staff),
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return HTMLResponse("Run not found", status_code=404)
    if admin.role != "admin" and run.owner_user_id != admin.id:
        return HTMLResponse("Not authorized", status_code=403)
    job_id = run.job_id
    db.delete(run)
    db.commit()
    log_event(
        db,
        action="run_deleted",
        actor_user_id=admin.id,
        target_type="run",
        target_id=str(run_id),
        details={"job_id": job_id},
    )
    return RedirectResponse(url="/admin/runs", status_code=303)
