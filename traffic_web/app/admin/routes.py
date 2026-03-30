from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth.deps import get_db, require_staff
from ..auth.passwords import verify_password, hash_password
from ..auth.rate_limit import is_rate_limited, log_attempt
from ..auth.sessions import SESSION_COOKIE_NAME, create_session, revoke_session
from ..db.models import User, Run
from ..services.audit import log_event
from .stats import compute_dashboard_stats
from .users import router as users_router
from .runs import router as runs_router
from .zones import router as zones_router
from .presets import router as presets_router


router = APIRouter(prefix="/admin", tags=["admin"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router.include_router(users_router)
router.include_router(runs_router)
router.include_router(zones_router)
router.include_router(presets_router)


def _safe_next(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return None
    return value


def _as_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _extract_location(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    lat = _as_float(raw.get("lat"))
    lon = _as_float(raw.get("lon"))
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    out = {"lat": lat, "lon": lon}
    address = raw.get("address")
    if isinstance(address, str) and address.strip():
        out["address"] = address.strip()
    return out


def _load_locations_by_job_id(data_dir: Path) -> dict[str, dict]:
    jobs_file = data_dir / "jobs.json"
    if not jobs_file.exists():
        return {}
    try:
        payload = json.loads(jobs_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict] = {}
    for job_id, job in payload.items():
        if not isinstance(job, dict):
            continue
        loc = _extract_location(job.get("location"))
        if loc:
            out[str(job_id)] = loc
    return out


def _safe_json_obj(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _location_from_run(run: Run, locations_by_job_id: dict[str, dict]) -> dict | None:
    if run.job_id in locations_by_job_id:
        return locations_by_job_id[run.job_id]
    cfg = _safe_json_obj(run.config_json)
    direct = _extract_location(cfg)
    if direct:
        return direct
    intersection = cfg.get("intersection")
    return _extract_location(intersection)


def _normalize_place_key(place: str) -> str:
    return " ".join(place.strip().lower().split())


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_object(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_geocode_cache(data_dir: Path) -> dict[str, dict]:
    raw = _read_json_object(data_dir / "geocode_cache.json")
    out: dict[str, dict] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        loc = _extract_location(value)
        if loc:
            out[key] = loc
    return out


def _save_geocode_cache(data_dir: Path, cache: dict[str, dict]) -> None:
    _write_json_object(data_dir / "geocode_cache.json", cache)


def _geocode_place(place: str) -> dict | None:
    q = place.strip()
    if not q:
        return None
    url = f"https://nominatim.openstreetmap.org/search?{urlencode({'format': 'json', 'limit': 1, 'q': q})}"
    req = UrlRequest(url, headers={"User-Agent": "TrafficTrackerAdmin/1.0"})
    try:
        with urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    loc = _extract_location({"lat": first.get("lat"), "lon": first.get("lon"), "address": first.get("display_name")})
    return loc


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    next_url = _safe_next(request.query_params.get("next"))
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "next": next_url},
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = Form(None),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    next_url = _safe_next(next)
    if is_rate_limited(db, username=username, ip=client_ip):
        log_attempt(db, username=username, ip=client_ip, success=False)
        log_event(
            db,
            action="login_rate_limited",
            actor_user_id=None,
            target_type="user",
            target_id=username,
            details={"username": username},
            ip=client_ip,
        )
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Too many attempts. Try again later.", "next": next_url},
            status_code=429,
        )

    user = (
        db.query(User)
        .filter((User.username == username) | (User.email == username))
        .first()
    )
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        log_attempt(db, username=username, ip=client_ip, success=False)
        log_event(
            db,
            action="login_failed",
            actor_user_id=user.id if user else None,
            target_type="user",
            target_id=username,
            details={"username": username},
            ip=client_ip,
        )
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Invalid credentials.", "next": next_url},
            status_code=401,
        )

    log_attempt(db, username=username, ip=client_ip, success=True)
    user.last_login_at = datetime.utcnow()
    db.add(user)
    db.commit()

    token = create_session(
        db,
        user=user,
        ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    log_event(
        db,
        action="login_success",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        details={"username": username},
        ip=client_ip,
    )
    if user.role == "viewer" and next_url and next_url.startswith("/admin"):
        next_url = None
    default_dest = "/admin" if user.role in ("admin", "user") else "/"
    response = RedirectResponse(url=next_url or default_dest, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        revoke_session(db, token)
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(require_staff),
):
    form = {
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name or "",
    }
    return templates.TemplateResponse(
        "admin/profile.html",
        {"request": request, "user": user, "form": form},
    )


@router.post("/profile", response_class=HTMLResponse)
def profile_update(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(""),
    new_password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    email = email.strip().lower()
    username = username.strip()
    full_name = full_name.strip()
    form = {
        "email": email,
        "username": username,
        "full_name": full_name,
    }
    email_owner = db.query(User).filter(User.email == email, User.id != user.id).first()
    if email_owner:
        return templates.TemplateResponse(
            "admin/profile.html",
            {"request": request, "user": user, "form": form, "error": "Email already exists."},
            status_code=400,
        )
    username_owner = db.query(User).filter(User.username == username, User.id != user.id).first()
    if username_owner:
        return templates.TemplateResponse(
            "admin/profile.html",
            {"request": request, "user": user, "form": form, "error": "Username already exists."},
            status_code=400,
        )

    user.email = email
    user.username = username
    user.full_name = full_name
    if new_password.strip():
        user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()
    log_event(
        db,
        action="user_profile_updated",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        details={"email": email, "username": username},
    )
    return templates.TemplateResponse(
        "admin/profile.html",
        {"request": request, "user": user, "form": form, "success": "Profile updated."},
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    owner_id = None if user.role == "admin" else user.id
    stats = compute_dashboard_stats(db, owner_user_id=owner_id)
    recent_query = db.query(Run).order_by(Run.created_at.desc())
    if owner_id:
        recent_query = recent_query.filter(Run.owner_user_id == owner_id)
    recent_runs = recent_query.limit(20).all()
    map_query = db.query(Run).order_by(Run.created_at.desc())
    if owner_id:
        map_query = map_query.filter(Run.owner_user_id == owner_id)
    map_runs_raw = map_query.limit(1000).all()
    data_dir = BASE_DIR / "_data"
    locations_by_job_id = _load_locations_by_job_id(data_dir)
    geocode_cache = _load_geocode_cache(data_dir)
    geocode_cache_changed = False
    geocode_budget = 12
    map_runs: list[dict] = []
    for run in map_runs_raw:
        if not run.job_id:
            continue
        loc = _location_from_run(run, locations_by_job_id)
        if not loc and isinstance(run.place, str) and run.place.strip():
            key = _normalize_place_key(run.place)
            loc = geocode_cache.get(key)
            if not loc and geocode_budget > 0:
                geocode_budget -= 1
                loc = _geocode_place(run.place)
                if loc:
                    geocode_cache[key] = loc
                    geocode_cache_changed = True
        if not loc:
            continue
        map_runs.append(
            {
                "id": run.id,
                "job_id": run.job_id,
                "title": run.title or "",
                "place": run.place or "",
                "status": run.status or "",
                "recorded_at": run.recorded_at.isoformat() if run.recorded_at else "",
                "lat": loc["lat"],
                "lon": loc["lon"],
                "address": loc.get("address", ""),
                "run_url": f"/admin/runs/{run.id}",
                "result_url": f"/results/{run.job_id}",
            }
        )
    if geocode_cache_changed:
        _save_geocode_cache(data_dir, geocode_cache)
    google_maps_api_key = (os.getenv("TRAFFIC_TRACKER_GOOGLE_MAPS_API_KEY") or "").strip()
    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_runs": recent_runs,
            "map_runs": map_runs,
            "google_maps_api_key": google_maps_api_key,
        },
    )
