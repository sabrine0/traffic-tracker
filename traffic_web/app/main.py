# traffic_web/app/main.py
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
import os
import json
import uuid
import shutil
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import cv2

from fastapi import FastAPI, Request, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.wsgi import WSGIMiddleware

from .store import Store
from .pipeline import process_video
from .xlsx_writer import write_xlsx
from .map2cad import create_map2cad_wsgi_app, get_map2cad_index_path
from .config.loader import load_config, resolve_model_path
from .admin.routes import router as admin_router
from .db.init_db import init_db
from .db.session import SessionLocal
from .auth.bootstrap import ensure_admin_user
from .auth.deps import get_db, get_current_user, require_editor
from .auth.sessions import SESSION_COOKIE_NAME, get_user_by_session
from .db.models import Run, User
from .services.runs import create_run, update_run


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "_data"

UPLOADS_DIR = STATIC_DIR / "uploads"
FRAMES_DIR = STATIC_DIR / "frames"
OUTPUTS_DIR = STATIC_DIR / "outputs"
ZONES_DIR = STATIC_DIR / "jobs"

CONFIG = load_config()
MODEL_PATH = resolve_model_path(BASE_DIR, CONFIG)

for d in [UPLOADS_DIR, FRAMES_DIR, OUTPUTS_DIR, DATA_DIR, ZONES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

_default_zone_labels = [f"V{i}" for i in range(1, 14)] + [f"P{i}" for i in range(1, 14)]
_classes_cfg = CONFIG.get("classes", {})
_zone_cfg = CONFIG.get("zones", {})

ZONE_LABELS = _zone_cfg.get("labels") if isinstance(_zone_cfg.get("labels"), list) else _default_zone_labels
ZONE_LABELS = [str(z) for z in ZONE_LABELS] if ZONE_LABELS else _default_zone_labels

CLASS_OPTIONS = _classes_cfg.get("options") if isinstance(_classes_cfg.get("options"), dict) else {}
if not CLASS_OPTIONS:
    CLASS_OPTIONS = {
        "person": {"id": 0, "label": "Person"},
        "bicycle": {"id": 1, "label": "Bicycle"},
        "car": {"id": 2, "label": "Car"},
        "motorcycle": {"id": 3, "label": "Motorcycle"},
        "bus": {"id": 5, "label": "Bus"},
        "truck": {"id": 7, "label": "Truck"},
    }

CLASS_ORDER = _classes_cfg.get("order") if isinstance(_classes_cfg.get("order"), list) else []
CLASS_ORDER = [str(k) for k in CLASS_ORDER if str(k) in CLASS_OPTIONS]
if not CLASS_ORDER:
    CLASS_ORDER = ["person", "bicycle", "car", "motorcycle", "bus", "truck"]

DEFAULT_CLASSES = _classes_cfg.get("default") if isinstance(_classes_cfg.get("default"), list) else []
DEFAULT_CLASSES = [str(k) for k in DEFAULT_CLASSES if str(k) in CLASS_OPTIONS]
if not DEFAULT_CLASSES:
    DEFAULT_CLASSES = ["car", "motorcycle", "bus", "truck", "person"]
DEVICE_ORDER = ["auto", "gpu", "cpu"]
DEVICE_OPTIONS = {
    "auto": "Auto (GPU if available)",
    "gpu": "GPU",
    "cpu": "CPU",
}
_model_cfg = CONFIG.get("model", {}) if isinstance(CONFIG.get("model"), dict) else {}
DEFAULT_DEVICE = _model_cfg.get("device_default") if isinstance(_model_cfg.get("device_default"), str) else "auto"

_TRACKING_CFG = CONFIG.get("tracking", {}) if isinstance(CONFIG.get("tracking"), dict) else {}
_VIDEO_CFG = CONFIG.get("video", {}) if isinstance(CONFIG.get("video"), dict) else {}

store = Store(DATA_DIR, ZONES_DIR)

app = FastAPI(title="Traffic Tracker")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.include_router(admin_router)
app.mount("/map2cad-api", WSGIMiddleware(create_map2cad_wsgi_app()))


def _is_public_path(path: str) -> bool:
    if path in ("/admin/login", "/admin/login/"):
        return True
    if path in ("/health", "/ping"):
        return True
    if path == "/static/styles.css":
        return True
    return False


def _get_db_for_request(request: Request):
    override = request.app.dependency_overrides.get(get_db)
    if override:
        gen = override()
    else:
        gen = get_db()
    try:
        db = next(gen)
    except StopIteration:
        return None, None
    return db, gen


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if _is_public_path(path):
        return await call_next(request)

    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = None
    if token:
        db, gen = _get_db_for_request(request)
        try:
            if db:
                user = get_user_by_session(db, token)
        finally:
            if gen:
                gen.close()

    if not user:
        if path.startswith("/api"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        next_path = path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        next_param = quote(next_path, safe="")
        return RedirectResponse(url=f"/admin/login?next={next_param}", status_code=303)

    request.state.user = user
    return await call_next(request)

@app.get("/static/outputs/{job_id}/{filename}")
def protected_output(
    job_id: str,
    filename: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    run = db.query(Run).filter(Run.job_id == job_id).first()
    if run:
        if user.role != "admin" and run.owner_user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        if user.role != "admin":
            raise HTTPException(status_code=404, detail="Run not found")
    job_dir = (OUTPUTS_DIR / job_id).resolve()
    file_path = (job_dir / filename).resolve()
    if not str(file_path).startswith(str(job_dir)):
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


@app.get("/static/frames/{filename}")
def protected_frame(
    filename: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job_id = filename.split("_", 1)[0]
    run = db.query(Run).filter(Run.job_id == job_id).first()
    if run:
        if user.role != "admin" and run.owner_user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        if user.role != "admin":
            raise HTTPException(status_code=404, detail="Video not found")
    frames_dir = FRAMES_DIR.resolve()
    file_path = (frames_dir / filename).resolve()
    if not str(file_path).startswith(str(frames_dir)):
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


@app.get("/static/uploads/{filename}")
def protected_upload(
    filename: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job_id = filename.split("_", 1)[0]
    run = db.query(Run).filter(Run.job_id == job_id).first()
    if run:
        if user.role != "admin" and run.owner_user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        if user.role != "admin":
            raise HTTPException(status_code=404, detail="Video not found")
    uploads_dir = UPLOADS_DIR.resolve()
    file_path = (uploads_dir / filename).resolve()
    if not str(file_path).startswith(str(uploads_dir)):
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def _startup() -> None:
    if os.getenv("TRAFFIC_TRACKER_AUTO_CREATE", "1") == "1":
        init_db()
    if os.getenv("TRAFFIC_TRACKER_ADMIN_EMAIL") and os.getenv("TRAFFIC_TRACKER_ADMIN_PASSWORD"):
        db = SessionLocal()
        try:
            ensure_admin_user(db)
        finally:
            db.close()

DEFAULT_ZONES = {
    "entry": {k: [] for k in ZONE_LABELS},
    "exit": {k: [] for k in ZONE_LABELS},
}

JOB_EXECUTOR = ThreadPoolExecutor(max_workers=1)
JOB_LOCK = threading.Lock()
RUNNING_JOBS: set[str] = set()


def extract_first_frame(video_path: Path, out_png: Path) -> None:
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Could not read first frame from video.")
    cv2.imwrite(str(out_png), frame)


def _parse_ffprobe_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        if "." in text:
            base = text.split(".", 1)[0]
            try:
                return datetime.fromisoformat(base)
            except ValueError:
                return None
    return None


def _probe_creation_time(video_path: Path) -> datetime | None:
    for query in ("format_tags=creation_time", "stream_tags=creation_time"):
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            query,
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return None
        value = (result.stdout or "").strip()
        if not value:
            continue
        parsed = _parse_ffprobe_datetime(value)
        if parsed:
            return parsed
    return None


def _parse_recorded_at(date_value: str | None, time_value: str | None) -> datetime | None:
    date_value = (date_value or "").strip()
    time_value = (time_value or "").strip()
    if date_value and time_value:
        try:
            return datetime.fromisoformat(f"{date_value} {time_value}")
        except ValueError:
            return None
    if date_value:
        try:
            return datetime.fromisoformat(f"{date_value} 00:00")
        except ValueError:
            return None
    return None

def _mark_running(job_id: str, running: bool) -> None:
    with JOB_LOCK:
        if running:
            RUNNING_JOBS.add(job_id)
        else:
            RUNNING_JOBS.discard(job_id)


def _is_running(job_id: str) -> bool:
    with JOB_LOCK:
        return job_id in RUNNING_JOBS


def _normalize_classes(classes: list[str] | None) -> list[str]:
    if not classes:
        return DEFAULT_CLASSES[:]
    normalized = [c for c in classes if c in CLASS_OPTIONS]
    return normalized or DEFAULT_CLASSES[:]


def _normalize_device(value: str | None) -> str:
    if value is None:
        return DEFAULT_DEVICE
    key = str(value).strip().lower()
    if key in DEVICE_OPTIONS:
        return key
    if key in ("cuda", "cuda:0", "0", "gpu0"):
        return "gpu"
    if key in ("cpu", "-1"):
        return "cpu"
    return DEFAULT_DEVICE


def _collect_zone_names(zones: dict | None, entry_counts: dict, exit_counts: dict, od_counts: dict) -> list[str]:
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names:
            names.append(name)

    if isinstance(zones, dict):
        for t in ("entry", "exit"):
            zdict = zones.get(t)
            if isinstance(zdict, dict):
                for k in zdict.keys():
                    add(str(k))

    for k in entry_counts.keys():
        add(str(k))
    for k in exit_counts.keys():
        add(str(k))
    for k in od_counts.keys():
        if "->" in k:
            a, b = k.split("->", 1)
            add(a)
            add(b)

    if not names:
        names = ZONE_LABELS[:]

    ordered = [z for z in ZONE_LABELS if z in names]
    for z in names:
        if z not in ordered:
            ordered.append(z)
    return ordered


def _is_vehicle_zone(name: str) -> bool:
    return str(name).upper().startswith("V")


def _default_intersection_config(approaches: list[str], location: dict | None = None) -> dict:
    cycle_length = 90
    saturation_flow = 1800
    phf = 0.92
    heavy_pct = 5.0
    hvf = 1.0 / (1.0 + (heavy_pct / 100.0))
    default_names = ["North", "South", "East", "West"]
    approach_list = approaches[:] if approaches else default_names
    approach_count = max(1, len(approach_list))
    default_green = max(10, int(round(cycle_length / float(approach_count))))
    lane_groups = {}
    for name in approach_list:
        lane_groups[str(name)] = {
            "left": 1,
            "through": 1,
            "right": 0,
            "lt": 0,
            "tr": 0,
        }
    phases = []
    if len(approach_list) >= 2:
        half = max(1, len(approach_list) // 2)
        phase1_moves = []
        phase2_moves = []
        for name in approach_list[:half]:
            phase1_moves.append(f"{name}:through")
            phase1_moves.append(f"{name}:right")
        for name in approach_list[half:]:
            phase2_moves.append(f"{name}:through")
            phase2_moves.append(f"{name}:right")
        phases = [
            {"name": "Phase 1", "green": default_green, "movements": phase1_moves},
            {"name": "Phase 2", "green": default_green, "movements": phase2_moves},
        ]
    cfg = {
        "name": "",
        "city": "",
        "lat": None,
        "lon": None,
        "saturation_flow": saturation_flow,
        "cycle_length": cycle_length,
        "phf": phf,
        "heavy_pct": heavy_pct,
        "hvf": hvf,
        "approaches": approach_list,
        "lane_groups": lane_groups,
        "zone_map": {},
        "movement_map": {},
        "phases": phases,
    }
    if isinstance(location, dict):
        try:
            cfg["lat"] = float(location.get("lat"))
            cfg["lon"] = float(location.get("lon"))
        except Exception:
            pass
    return cfg


def _normalize_intersection_config(
    cfg: dict | None,
    approaches: list[str],
    location: dict | None = None,
) -> dict:
    base = _default_intersection_config(approaches, location=location)
    if not isinstance(cfg, dict):
        return base
    out = dict(base)
    out["name"] = str(cfg.get("name") or base["name"])
    out["city"] = str(cfg.get("city") or base["city"])
    for key in ("lat", "lon"):
        val = cfg.get(key)
        if isinstance(val, (int, float)):
            out[key] = float(val)
        elif isinstance(val, str):
            try:
                out[key] = float(val)
            except Exception:
                pass

    sat_flow = cfg.get("saturation_flow")
    if isinstance(sat_flow, (int, float)) and sat_flow > 0:
        out["saturation_flow"] = float(sat_flow)
    cycle = cfg.get("cycle_length")
    if isinstance(cycle, (int, float)) and cycle > 0:
        out["cycle_length"] = float(cycle)
    phf = cfg.get("phf")
    if isinstance(phf, (int, float)) and 0 < phf <= 1.0:
        out["phf"] = float(phf)
    heavy_pct = cfg.get("heavy_pct")
    if isinstance(heavy_pct, (int, float)) and heavy_pct >= 0:
        out["heavy_pct"] = float(heavy_pct)
    hvf = cfg.get("hvf")
    if isinstance(hvf, (int, float)) and 0 < hvf <= 1.0:
        out["hvf"] = float(hvf)

    approach_list = cfg.get("approaches")
    if isinstance(approach_list, list) and approach_list:
        cleaned = [str(a).strip() for a in approach_list if str(a).strip()]
        if cleaned:
            out["approaches"] = cleaned

    zone_map = cfg.get("zone_map")
    if isinstance(zone_map, dict):
        out["zone_map"] = {str(k): str(v) for k, v in zone_map.items()}

    movement_map = cfg.get("movement_map")
    if isinstance(movement_map, dict):
        out["movement_map"] = {str(k): str(v) for k, v in movement_map.items()}

    lane_groups = {}
    existing_groups = cfg.get("lane_groups") if isinstance(cfg.get("lane_groups"), dict) else {}
    for name in out["approaches"]:
        raw = existing_groups.get(str(name)) if isinstance(existing_groups, dict) else None
        if not isinstance(raw, dict):
            lane_groups[str(name)] = dict(base["lane_groups"].get(str(name), base["lane_groups"][out["approaches"][0]]))
            continue
        lane_groups[str(name)] = {
            "left": int(raw.get("left", 0) or 0),
            "through": int(raw.get("through", 0) or 0),
            "right": int(raw.get("right", 0) or 0),
            "lt": int(raw.get("lt", 0) or 0),
            "tr": int(raw.get("tr", 0) or 0),
        }
    out["lane_groups"] = lane_groups

    phases = cfg.get("phases") if isinstance(cfg.get("phases"), list) else []
    cleaned_phases = []
    for ph in phases:
        if not isinstance(ph, dict):
            continue
        name = str(ph.get("name") or "Phase")
        green = ph.get("green")
        try:
            green_val = float(green)
        except Exception:
            green_val = 0.0
        movements = ph.get("movements")
        if not isinstance(movements, list):
            movements = []
        cleaned_phases.append({
            "name": name,
            "green": green_val,
            "movements": [str(m) for m in movements if str(m)],
        })
    out["phases"] = cleaned_phases if cleaned_phases else base["phases"]
    return out


def _enforce_run_access(db, user: User, job_id: str) -> Run | None:
    run = db.query(Run).filter(Run.job_id == job_id).first()
    if user.role != "admin":
        if not run or run.owner_user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    return run


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


@app.get("/map2cad", response_class=HTMLResponse)
@app.get("/map2cad/", response_class=HTMLResponse)
def map2cad_page():
    index_path = get_map2cad_index_path()
    if index_path is None:
        raise HTTPException(status_code=503, detail="Map2CAD frontend assets are not built.")
    return FileResponse(str(index_path))


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, user: User = Depends(require_editor)):
    place = (request.query_params.get("place") or "").strip()
    address = (request.query_params.get("address") or "").strip()
    if not place and address:
        place = address

    lat_form = ""
    lon_form = ""
    lat_q = request.query_params.get("lat")
    lon_q = request.query_params.get("lon")
    try:
        lat_val = float(lat_q) if lat_q is not None else None
        lon_val = float(lon_q) if lon_q is not None else None
        if lat_val is not None and lon_val is not None and -90 <= lat_val <= 90 and -180 <= lon_val <= 180:
            lat_form = f"{lat_val:.6f}"
            lon_form = f"{lon_val:.6f}"
    except Exception:
        lat_form = ""
        lon_form = ""

    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "user": user,
            "form": {
                "title": "",
                "place": place,
                "date": "",
                "time": "",
                "lat": lat_form,
                "lon": lon_form,
                "address": address,
            },
        },
    )


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, user: User = Depends(get_current_user), db=Depends(get_db)):
    jobs = store.list_jobs()
    if user.role != "admin":
        allowed_ids = {
            r.job_id
            for r in db.query(Run).filter(Run.owner_user_id == user.id).all()
        }
        jobs = [j for j in jobs if j.get("id") in allowed_ids]
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs, "user": user})


@app.post("/upload", response_class=HTMLResponse)
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    place: str = Form(""),
    date_value: str | None = Form(None, alias="date"),
    time_value: str | None = Form(None, alias="time"),
    lat: str | None = Form(None),
    lon: str | None = Form(None),
    address: str | None = Form(None),
    user: User = Depends(require_editor),
    db=Depends(get_db),
):
    job_id = uuid.uuid4().hex[:8]

    place = place.strip()
    title = title.strip()
    if not place:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "user": user,
                "error": "Place is required.",
                "form": {
                    "title": title,
                    "place": place,
                    "date": date_value,
                    "time": time_value,
                    "lat": lat or "",
                    "lon": lon or "",
                    "address": address or "",
                },
            },
            status_code=400,
        )

    safe_name = file.filename.replace(" ", "_")
    video_path = UPLOADS_DIR / f"{job_id}_{safe_name}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    recorded_at = _parse_recorded_at(date_value, time_value)
    if recorded_at is None and not (date_value and time_value):
        recorded_at = _probe_creation_time(video_path)

    if not title:
        if recorded_at:
            title = f"{place} - {recorded_at.strftime('%Y-%m-%d %H:%M')}"
        else:
            title = Path(safe_name).stem

    store.create_job(job_id, str(video_path))
    create_run(
        db,
        job_id=job_id,
        video_filename=safe_name,
        title=title,
        place=place,
        recorded_at=recorded_at,
        owner_user_id=user.id,
    )

    loc = None
    lat_val = None
    lon_val = None
    try:
        if lat:
            lat_val = float(lat)
    except Exception:
        lat_val = None
    try:
        if lon:
            lon_val = float(lon)
    except Exception:
        lon_val = None
    if lat_val is not None and lon_val is not None and -90 <= lat_val <= 90 and -180 <= lon_val <= 180:
        loc = {"lat": lat_val, "lon": lon_val}
        addr = (address or "").strip()
        if addr:
            loc["address"] = addr
        elif place:
            loc["address"] = place
    if loc:
        store.update_job(job_id, location=loc)

    frame_path = FRAMES_DIR / f"{job_id}_frame0.png"
    extract_first_frame(video_path, frame_path)

    return RedirectResponse(url=f"/results/{job_id}", status_code=303)


@app.get("/results/{job_id}", response_class=HTMLResponse)
def results_page(
    request: Request,
    job_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    _enforce_run_access(db, user, job_id)
    job = store.get_job(job_id)
    if not job:
        return HTMLResponse("Video not found", status_code=404)

    raw_status = job.get("status") or "uploaded"
    status = "processing" if raw_status == "running" else raw_status
    error = job.get("error")
    outputs = job.get("outputs") or {}

    logs = job.get("logs") or []
    settings = job.get("settings") or {}
    selected_classes = _normalize_classes(settings.get("classes"))
    selected_device = _normalize_device(settings.get("device"))
    class_options = [{"key": k, "label": CLASS_OPTIONS[k]["label"]} for k in CLASS_ORDER]
    device_options = [{"key": k, "label": DEVICE_OPTIONS[k]} for k in DEVICE_ORDER]
    device_label = DEVICE_OPTIONS.get(selected_device, selected_device)

    metrics = job.get("metrics") or {}
    if not metrics and outputs.get("results_json"):
        results = store.get_results(job_id)
        if results:
            metrics = {
                "entry_counts": results.get("entry_counts", {}),
                "exit_counts": results.get("exit_counts", {}),
                "od_counts": results.get("od_counts", {}),
                "tracks": results.get("tracks", []),
                "class_counts": results.get("class_counts", {}),
                "classes": results.get("classes", []),
            }

    entry_counts = metrics.get("entry_counts", {})
    exit_counts = metrics.get("exit_counts", {})
    od_counts = metrics.get("od_counts", {})

    class_counts = metrics.get("class_counts") or {}
    class_counts = {str(k): int(v) for k, v in class_counts.items()}
    classes_used = metrics.get("classes") or selected_classes
    used_keys = [str(k) for k in classes_used]
    class_count_rows = []
    for key in used_keys:
        label = CLASS_OPTIONS.get(key, {}).get("label", key.title())
        class_count_rows.append({"label": label, "count": class_counts.get(key, 0)})
    for key, count in class_counts.items():
        if key in used_keys:
            continue
        label = CLASS_OPTIONS.get(key, {}).get("label", key.title())
        class_count_rows.append({"label": label, "count": int(count)})

    zones = store.get_zones(job_id) or {}
    zone_names = _collect_zone_names(zones, entry_counts, exit_counts, od_counts)

    zone_rows = []
    for z in zone_names:
        zone_rows.append({
            "zone": z,
            "entry": int(entry_counts.get(z, 0)),
            "exit": int(exit_counts.get(z, 0)),
        })

    od_rows = []
    for k, v in od_counts.items():
        if "->" not in k:
            continue
        entry, exit_ = k.split("->", 1)
        od_rows.append({"entry": entry, "exit": exit_, "count": int(v)})
    od_rows.sort(key=lambda r: r["count"], reverse=True)

    od_matrix_rows = []
    for entry in zone_names:
        counts = []
        for exit_ in zone_names:
            counts.append(int(od_counts.get(f"{entry}->{exit_}", 0)))
        od_matrix_rows.append({"entry": entry, "counts": counts})

    od_matrix = {"cols": zone_names, "rows": od_matrix_rows}

    progress = None
    if status == "processing":
        frame_processed = metrics.get("frame_processed")
        frame_total = metrics.get("frame_total")
        if frame_processed is not None and frame_total:
            percent = (float(frame_processed) / float(frame_total)) * 100.0
            progress = {
                "processed": int(frame_processed),
                "total": int(frame_total),
                "percent": round(percent, 1),
            }

    location = job.get("location")
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "user": user,
            "job_id": job_id,
            "status": status,
            "error": error,
            "outputs": outputs,
            "metrics": metrics,
            "logs": logs,
            "class_options": class_options,
            "selected_classes": selected_classes,
            "device_options": device_options,
            "selected_device": selected_device,
            "device_label": device_label,
            "class_count_rows": class_count_rows,
            "progress": progress,
            "zone_rows": zone_rows,
            "od_rows": od_rows,
            "od_matrix": od_matrix,
            "location": location,
        },
    )


@app.get("/intersection/{job_id}", response_class=HTMLResponse)
def intersection_page(
    request: Request,
    job_id: str,
    user: User = Depends(require_editor),
    db=Depends(get_db),
):
    _enforce_run_access(db, user, job_id)
    job = store.get_job(job_id)
    if not job:
        return HTMLResponse("Video not found", status_code=404)

    outputs = job.get("outputs") or {}
    metrics = job.get("metrics") or {}
    if not metrics and outputs.get("results_json"):
        results = store.get_results(job_id)
        if results:
            metrics = {
                "entry_counts": results.get("entry_counts", {}),
                "exit_counts": results.get("exit_counts", {}),
                "od_counts": results.get("od_counts", {}),
                "tracks": results.get("tracks", []),
                "class_counts": results.get("class_counts", {}),
                "classes": results.get("classes", []),
                "frame_count": results.get("frame_count"),
                "fps": results.get("fps"),
                "duration_sec": results.get("duration_sec"),
            }

    entry_counts = metrics.get("entry_counts", {})
    exit_counts = metrics.get("exit_counts", {})
    od_counts = metrics.get("od_counts", {}) or {}
    zones = store.get_zones(job_id) or {}
    zone_names = _collect_zone_names(zones, entry_counts, exit_counts, od_counts)
    vehicle_zones = [z for z in zone_names if _is_vehicle_zone(str(z))]

    cfg_seed = job.get("intersection") or {}
    approach_seed = cfg_seed.get("approaches") if isinstance(cfg_seed, dict) else None
    if not isinstance(approach_seed, list) or not approach_seed:
        approach_seed = ["North", "South", "East", "West"]

    duration_sec = metrics.get("duration_sec")
    if not duration_sec:
        frame_count = metrics.get("frame_count")
        fps = metrics.get("fps")
        if frame_count and fps:
            try:
                duration_sec = float(frame_count) / float(fps)
            except Exception:
                duration_sec = None
    duration_hours = (float(duration_sec) / 3600.0) if duration_sec else None

    od_rows = []
    for k, v in od_counts.items():
        entry = None
        exit_ = None
        if isinstance(k, str) and "->" in k:
            entry, exit_ = k.split("->", 1)
        elif isinstance(k, (list, tuple)) and len(k) == 2:
            entry, exit_ = k[0], k[1]
        if entry is None or exit_ is None:
            continue
        try:
            count = int(v)
        except Exception:
            count = 0
        od_rows.append({"entry": str(entry), "exit": str(exit_), "count": count})
    od_rows.sort(key=lambda r: r["count"], reverse=True)

    cfg = _normalize_intersection_config(job.get("intersection"), approach_seed, location=job.get("location"))

    return templates.TemplateResponse(
        "intersection.html",
        {
            "request": request,
            "user": user,
            "job_id": job_id,
            "duration_hours": duration_hours,
            "approaches": cfg.get("approaches", approach_seed),
            "od_zone_rows": od_rows,
            "vehicle_zones": vehicle_zones,
            "intersection_config": cfg,
            "location": job.get("location"),
        },
    )


@app.get("/zones/{job_id}", response_class=HTMLResponse)
def zones_editor(request: Request, job_id: str, user: User = Depends(require_editor), db=Depends(get_db)):
    _enforce_run_access(db, user, job_id)
    job = store.get_job(job_id)
    if not job:
        return HTMLResponse("Video not found", status_code=404)

    frame_url = f"/static/frames/{job_id}_frame0.png"
    zones = store.get_zones(job_id) or DEFAULT_ZONES

    return templates.TemplateResponse(
        "zones_editor.html",
        {
            "request": request,
            "user": user,
            "job_id": job_id,
            "frame_url": frame_url,
            "zones_json": zones,
            "zone_labels": ZONE_LABELS,
        },
    )


@app.post("/api/settings/{job_id}")
async def api_save_settings(job_id: str, request: Request, user: User = Depends(require_editor), db=Depends(get_db)):
    _enforce_run_access(db, user, job_id)
    job = store.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "video not found"}, status_code=404)
    payload = await request.json()
    settings = job.get("settings") or {}
    classes = payload.get("classes", settings.get("classes"))
    if classes is None or not isinstance(classes, list):
        return JSONResponse({"ok": False, "error": "classes must be a list"}, status_code=400)
    selected = _normalize_classes([str(c) for c in classes])
    selected_device = _normalize_device(payload.get("device", settings.get("device")))
    settings["classes"] = selected
    settings["device"] = selected_device
    store.update_job(job_id, settings=settings)
    return {"ok": True, "classes": selected, "device": selected_device}


@app.post("/api/zones/{job_id}")
async def api_save_zones(job_id: str, request: Request, user: User = Depends(require_editor), db=Depends(get_db)):
    _enforce_run_access(db, user, job_id)
    payload = await request.json()
    if "entry" not in payload or "exit" not in payload:
        return JSONResponse({"ok": False, "error": "zones must contain entry + exit"}, status_code=400)

    store.set_zones(job_id, payload)
    return {"ok": True}


@app.post("/api/intersection/{job_id}")
async def api_save_intersection(
    job_id: str,
    request: Request,
    user: User = Depends(require_editor),
    db=Depends(get_db),
):
    _enforce_run_access(db, user, job_id)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "payload must be an object"}, status_code=400)
    store.update_job(job_id, intersection=payload)
    return {"ok": True}


@app.post("/api/intersection_report/{job_id}")
async def api_intersection_report(
    job_id: str,
    request: Request,
    user: User = Depends(require_editor),
    db=Depends(get_db),
):
    _enforce_run_access(db, user, job_id)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "payload must be an object"}, status_code=400)

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return JSONResponse({"ok": False, "error": "rows required"}, status_code=400)

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}

    results = store.get_results(job_id)
    if not results:
        return JSONResponse({"ok": False, "error": "results not found"}, status_code=400)

    zone_names = results.get("zone_names") or []
    entry_counts = results.get("entry_counts") or {}
    exit_counts = results.get("exit_counts") or {}
    od_counts = results.get("od_counts") or {}
    tracks = results.get("tracks") or []
    files = results.get("files") or {}

    frame_count = results.get("frame_count") or 0
    fps = results.get("fps") or 0
    duration_sec = results.get("duration_sec")
    if duration_sec is None and frame_count and fps:
        try:
            duration_sec = float(frame_count) / float(fps)
        except Exception:
            duration_sec = None
    od_flows = sum(int(v) for v in od_counts.values()) if isinstance(od_counts, dict) else 0

    summary_rows = [
        ["Job ID", results.get("job_id") or job_id],
        ["Video", results.get("video")],
        ["Frames", frame_count],
        ["FPS", round(float(fps), 2) if fps else fps],
        ["Duration (sec)", round(float(duration_sec), 2) if duration_sec else duration_sec],
        ["Tracks", len(tracks)],
        ["OD Flows", od_flows],
        ["Classes", ", ".join(results.get("classes") or [])],
    ]

    counts_rows = [["Zone", "Entry Count", "Exit Count"]]
    for z in zone_names:
        counts_rows.append([z, int(entry_counts.get(z, 0)), int(exit_counts.get(z, 0))])

    od_header = ["Entry / Exit"] + zone_names
    od_rows = [od_header]
    for entry in zone_names:
        row = [entry]
        for exit_ in zone_names:
            row.append(int(od_counts.get(f"{entry}->{exit_}", 0)))
        od_rows.append(row)

    tracks_rows = [["Track ID", "Entry Zone", "Exit Zone", "First Frame", "Last Frame"]]
    for t in tracks:
        tracks_rows.append([
            t.get("id"),
            t.get("entry") or "",
            t.get("exit") or "",
            int(t.get("first_frame") or 0),
            int(t.get("last_frame") or 0),
        ])

    files_rows = [
        ["Type", "Filename"],
        ["Overlay Video", files.get("overlay_video")],
        ["Heatmap", files.get("heatmap_image")],
        ["Heatmap Video", files.get("heatmap_video")],
        ["Results JSON", files.get("results_json")],
        ["Report XLSX", files.get("report_xlsx")],
    ]

    intersection_rows = []
    intersection_rows.append(["Intersection"])
    intersection_rows.append([])
    intersection_rows.append(["Meta"])
    intersection_rows.append(["Field", "Value"])
    for key, label in (
        ("name", "Name"),
        ("city", "City"),
        ("lat", "Lat"),
        ("lon", "Lon"),
        ("cycle_length", "Cycle length"),
        ("saturation_flow", "Saturation flow"),
        ("phf", "PHF"),
        ("hvf", "HVF"),
        ("heavy_pct", "Heavy %"),
    ):
        if key in meta:
            intersection_rows.append([label, meta.get(key)])
    intersection_rows.append([])
    intersection_rows.append(["Phases"])
    intersection_rows.append(["Phase", "Green (sec)", "Movements"])
    for ph in config.get("phases") if isinstance(config.get("phases"), list) else []:
        if isinstance(ph, dict):
            name = ph.get("name")
            green = ph.get("green")
            movements = ", ".join(ph.get("movements") or []) if isinstance(ph.get("movements"), list) else ""
            intersection_rows.append([name, green, movements])
    intersection_rows.append([])
    intersection_rows.append(["Lane Groups"])
    intersection_rows.append(["Approach", "Left", "Through", "Right", "LT", "TR"])
    lane_groups = config.get("lane_groups") if isinstance(config.get("lane_groups"), dict) else {}
    approach_list = config.get("approaches") if isinstance(config.get("approaches"), list) else list(lane_groups.keys())
    for a in approach_list:
        g = lane_groups.get(a, {}) if isinstance(lane_groups.get(a), dict) else {}
        intersection_rows.append([
            a,
            g.get("left", 0),
            g.get("through", 0),
            g.get("right", 0),
            g.get("lt", 0),
            g.get("tr", 0),
        ])
    intersection_rows.append([])
    intersection_rows.append(["v/c Table"])
    intersection_rows.append([
        "Approach",
        "Movement",
        "Lane Group",
        "Volume (veh/h)",
        "Lanes",
        "Green (sec)",
        "Capacity (veh/h)",
        "PHF",
        "HVF",
        "X",
        "Status",
    ])
    for r in rows:
        if not isinstance(r, dict):
            continue
        intersection_rows.append([
            r.get("approach"),
            r.get("movement"),
            r.get("group"),
            r.get("volume"),
            r.get("lanes"),
            r.get("green"),
            r.get("capacity"),
            r.get("phf"),
            r.get("hvf"),
            r.get("x"),
            r.get("status"),
        ])
    intersection_rows.append([])
    intersection_rows.append(["Summary"])
    intersection_rows.append(["Field", "Value"])
    for key in ("critical_group", "critical_x", "overall_status"):
        if key in summary:
            intersection_rows.append([key, summary.get(key)])
    intersection_rows.append([])
    intersection_rows.append(["Recommendations"])
    if recommendations:
        for r in recommendations:
            intersection_rows.append([r])
    else:
        intersection_rows.append(["No critical issues detected."])

    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    report_name = files.get("report_xlsx") or "report.xlsx"
    report_path = job_dir / report_name
    json_path = job_dir / "intersection_report.json"

    write_xlsx(report_path, [
        ("Summary", summary_rows),
        ("Counts by Zone", counts_rows),
        ("OD Matrix", od_rows),
        ("Tracks", tracks_rows),
        ("Files", files_rows),
        ("Intersection", intersection_rows),
    ])

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    job = store.get_job(job_id)
    outputs = (job.get("outputs") or {}) if job else {}
    if not outputs.get("report_xlsx"):
        outputs["report_xlsx"] = f"/static/outputs/{job_id}/{report_name}"
    outputs["intersection_report_json"] = f"/static/outputs/{job_id}/intersection_report.json"
    store.update_job(job_id, outputs=outputs)
    return {"ok": True, "xlsx": outputs["report_xlsx"], "json": outputs.get("intersection_report_json")}


def _run_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        return

    zones = store.get_zones(job_id)
    if not zones:
        store.update_job(job_id, status="failed", error="Zones not set")
        store.append_log(job_id, "failed: zones not set")
        db = SessionLocal()
        try:
            update_run(db, job_id=job_id, status="failed", finished_at=datetime.utcnow())
        finally:
            db.close()
        return

    try:
        store.update_job(job_id, status="processing", error=None)
        store.append_log(job_id, "processing started")
        db = SessionLocal()
        try:
            update_run(db, job_id=job_id, status="processing", started_at=datetime.utcnow())
        finally:
            db.close()

        settings = job.get("settings") or {}
        selected_classes = _normalize_classes(settings.get("classes"))
        class_ids = [CLASS_OPTIONS[c]["id"] for c in selected_classes]
        selected_device = _normalize_device(settings.get("device"))
        device_arg = None
        if selected_device == "gpu":
            device_arg = "cuda:0"
        elif selected_device == "cpu":
            device_arg = "cpu"

        def progress_cb(frame_i, frame_total, fps):
            store.update_progress(job_id, frame_i, frame_total, fps)

        conf = _TRACKING_CFG.get("conf", 0.25)
        iou = _TRACKING_CFG.get("iou", 0.5)
        min_exit_delay_frames = _TRACKING_CFG.get("min_exit_delay_frames", 5)
        max_width = _VIDEO_CFG.get("max_width", 1280)

        outputs, metrics = process_video(
            video_path=job["video_path"],
            zones=zones,
            out_dir=OUTPUTS_DIR,
            job_id=job_id,
            model_path=MODEL_PATH,
            conf=conf,
            iou=iou,
            max_width=max_width,
            min_exit_delay_frames=min_exit_delay_frames,
            class_ids=class_ids,
            class_names=selected_classes,
            device=device_arg,
            zone_labels=ZONE_LABELS,
            progress_cb=progress_cb,
        )

        outputs_web = {
            "overlay_video": f"/static/outputs/{outputs['overlay_video']}",
            "heatmap": f"/static/outputs/{outputs['heatmap']}",
            "heatmap_video": (
                f"/static/outputs/{outputs['heatmap_video']}"
                if outputs.get("heatmap_video")
                else None
            ),
            "results_json": f"/static/outputs/{outputs['results_json']}",
            "report_xlsx": f"/static/outputs/{outputs['report_xlsx']}",
        }

        store.update_job(job_id, status="done", outputs=outputs_web, metrics=metrics)
        db = SessionLocal()
        try:
            run_config = {
                "model_path": str(MODEL_PATH),
                "classes": selected_classes,
                "device": selected_device,
                "tracking": {
                    "conf": conf,
                    "iou": iou,
                    "min_exit_delay_frames": min_exit_delay_frames,
                },
                "video": {"max_width": max_width},
            }
            job_location = job.get("location")
            if isinstance(job_location, dict):
                try:
                    lat = float(job_location.get("lat"))
                    lon = float(job_location.get("lon"))
                except Exception:
                    lat = None
                    lon = None
                if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                    run_config["location"] = {"lat": lat, "lon": lon}
                    address = job_location.get("address")
                    if isinstance(address, str) and address.strip():
                        run_config["location"]["address"] = address.strip()
            update_run(
                db,
                job_id=job_id,
                status="done",
                outputs=outputs_web,
                metrics=metrics,
                config=run_config,
                finished_at=datetime.utcnow(),
            )
        finally:
            db.close()
        store.append_log(job_id, "processing done")

    except Exception as e:
        store.update_job(job_id, status="failed", error=str(e))
        store.append_log(job_id, f"failed: {e}")
        db = SessionLocal()
        try:
            update_run(db, job_id=job_id, status="failed", finished_at=datetime.utcnow())
        finally:
            db.close()


def _run_job_guarded(job_id: str) -> None:
    _mark_running(job_id, True)
    try:
        _run_job(job_id)
    finally:
        _mark_running(job_id, False)


@app.post("/api/process/{job_id}")
def api_process(job_id: str, force: bool = False, user: User = Depends(require_editor), db=Depends(get_db)):
    _enforce_run_access(db, user, job_id)
    job = store.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "video not found"}, status_code=404)

    zones = store.get_zones(job_id)
    if not zones:
        return JSONResponse({"ok": False, "error": "zones not set"}, status_code=400)

    if _is_running(job_id):
        return {"ok": True, "status": "processing"}

    status = job.get("status") or "uploaded"
    if status in ("processing", "running") and not force:
        return {"ok": True, "status": "processing"}

    if force:
        store.update_job(job_id, status="uploaded", error=None, outputs=None, metrics=None)

    JOB_EXECUTOR.submit(_run_job_guarded, job_id)
    return {"ok": True, "status": "restarted" if force else "started"}
