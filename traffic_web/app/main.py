# traffic_web/app/main.py
from __future__ import annotations

from pathlib import Path
import os
import uuid
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
import cv2

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .store import Store
from .pipeline import process_video


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "_data"

UPLOADS_DIR = STATIC_DIR / "uploads"
FRAMES_DIR = STATIC_DIR / "frames"
OUTPUTS_DIR = STATIC_DIR / "outputs"
ZONES_DIR = STATIC_DIR / "jobs"

MODEL_PATH = Path(os.getenv("TRAFFIC_TRACKER_MODEL", str(BASE_DIR.parent.parent / "yolov8n.pt"))).expanduser()
if not MODEL_PATH.is_absolute():
    MODEL_PATH = (BASE_DIR.parent.parent / MODEL_PATH).resolve()

for d in [UPLOADS_DIR, FRAMES_DIR, OUTPUTS_DIR, DATA_DIR, ZONES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ZONE_LABELS = [f"V{i}" for i in range(1, 14)] + [f"P{i}" for i in range(1, 14)]
CLASS_ORDER = ["person", "bicycle", "car", "motorcycle", "bus", "truck"]
CLASS_OPTIONS = {
    "person": {"id": 0, "label": "Person"},
    "bicycle": {"id": 1, "label": "Bicycle"},
    "car": {"id": 2, "label": "Car"},
    "motorcycle": {"id": 3, "label": "Motorcycle"},
    "bus": {"id": 5, "label": "Bus"},
    "truck": {"id": 7, "label": "Truck"},
}
DEFAULT_CLASSES = ["car", "motorcycle", "bus", "truck", "person"]

store = Store(DATA_DIR, ZONES_DIR)

app = FastAPI(title="Traffic Tracker")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request):
    jobs = store.list_jobs()
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs})


@app.post("/upload", response_class=HTMLResponse)
async def upload_video(request: Request, file: UploadFile = File(...)):
    job_id = uuid.uuid4().hex[:8]

    safe_name = file.filename.replace(" ", "_")
    video_path = UPLOADS_DIR / f"{job_id}_{safe_name}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    store.create_job(job_id, str(video_path))

    frame_path = FRAMES_DIR / f"{job_id}_frame0.png"
    extract_first_frame(video_path, frame_path)

    return RedirectResponse(url=f"/results/{job_id}", status_code=303)


@app.get("/results/{job_id}", response_class=HTMLResponse)
def results_page(request: Request, job_id: str):
    job = store.get_job(job_id)
    if not job:
        return HTMLResponse("Job not found", status_code=404)

    raw_status = job.get("status") or "uploaded"
    status = "processing" if raw_status == "running" else raw_status
    error = job.get("error")
    outputs = job.get("outputs") or {}

    logs = job.get("logs") or []
    settings = job.get("settings") or {}
    selected_classes = _normalize_classes(settings.get("classes"))
    class_options = [{"key": k, "label": CLASS_OPTIONS[k]["label"]} for k in CLASS_ORDER]

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

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "job_id": job_id,
            "status": status,
            "error": error,
            "outputs": outputs,
            "metrics": metrics,
            "logs": logs,
            "class_options": class_options,
            "selected_classes": selected_classes,
            "class_count_rows": class_count_rows,
            "progress": progress,
            "zone_rows": zone_rows,
            "od_rows": od_rows,
            "od_matrix": od_matrix,
        },
    )


@app.get("/zones/{job_id}", response_class=HTMLResponse)
def zones_editor(request: Request, job_id: str):
    job = store.get_job(job_id)
    if not job:
        return HTMLResponse("Job not found", status_code=404)

    frame_url = f"/static/frames/{job_id}_frame0.png"
    zones = store.get_zones(job_id) or DEFAULT_ZONES

    return templates.TemplateResponse(
        "zones_editor.html",
        {
            "request": request,
            "job_id": job_id,
            "frame_url": frame_url,
            "zones_json": zones,
            "zone_labels": ZONE_LABELS,
        },
    )


@app.post("/api/settings/{job_id}")
async def api_save_settings(job_id: str, request: Request):
    job = store.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "job not found"}, status_code=404)
    payload = await request.json()
    classes = payload.get("classes")
    if not isinstance(classes, list):
        return JSONResponse({"ok": False, "error": "classes must be a list"}, status_code=400)
    selected = _normalize_classes([str(c) for c in classes])
    settings = job.get("settings") or {}
    settings["classes"] = selected
    store.update_job(job_id, settings=settings)
    return {"ok": True, "classes": selected}


@app.post("/api/zones/{job_id}")
async def api_save_zones(job_id: str, request: Request):
    payload = await request.json()
    if "entry" not in payload or "exit" not in payload:
        return JSONResponse({"ok": False, "error": "zones must contain entry + exit"}, status_code=400)

    store.set_zones(job_id, payload)
    return {"ok": True}


def _run_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        return

    zones = store.get_zones(job_id)
    if not zones:
        store.update_job(job_id, status="failed", error="Zones not set")
        store.append_log(job_id, "failed: zones not set")
        return

    try:
        store.update_job(job_id, status="processing", error=None)
        store.append_log(job_id, "processing started")

        settings = job.get("settings") or {}
        selected_classes = _normalize_classes(settings.get("classes"))
        class_ids = [CLASS_OPTIONS[c]["id"] for c in selected_classes]

        def progress_cb(frame_i, frame_total, fps):
            store.update_progress(job_id, frame_i, frame_total, fps)

        outputs, metrics = process_video(
            video_path=job["video_path"],
            zones=zones,
            out_dir=OUTPUTS_DIR,
            job_id=job_id,
            model_path=MODEL_PATH,
            class_ids=class_ids,
            class_names=selected_classes,
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
        store.append_log(job_id, "processing done")

    except Exception as e:
        store.update_job(job_id, status="failed", error=str(e))
        store.append_log(job_id, f"failed: {e}")


def _run_job_guarded(job_id: str) -> None:
    _mark_running(job_id, True)
    try:
        _run_job(job_id)
    finally:
        _mark_running(job_id, False)


@app.post("/api/process/{job_id}")
def api_process(job_id: str, force: bool = False):
    job = store.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "job not found"}, status_code=404)

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
