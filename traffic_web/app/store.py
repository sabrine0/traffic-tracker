# traffic_web/app/store.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, Optional, List


@dataclass
class Job:
    id: str
    status: str            # uploaded | processing | done | failed
    video_path: str
    created_at: str
    zones_path: Optional[str] = None
    outputs: Optional[dict] = None
    metrics: Optional[dict] = None
    settings: Optional[dict] = None
    intersection: Optional[dict] = None
    location: Optional[dict] = None
    error: Optional[str] = None
    logs: Optional[list] = None


class Store:
    """
    Simple JSON-file store (no DB). Safe enough for local dev.
    """
    def __init__(self, data_dir: Path, zones_dir: Path):
        self.data_dir = data_dir
        self.zones_dir = zones_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.zones_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.data_dir / "jobs.json"
        self._lock = threading.Lock()
        if not self.jobs_file.exists():
            self.jobs_file.write_text("{}", encoding="utf-8")

    def _read_unlocked(self) -> Dict[str, Any]:
        text = self.jobs_file.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        return json.loads(text)

    def _write_unlocked(self, data: Dict[str, Any]) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="jobs_", suffix=".json", dir=str(self.jobs_file.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
            os.replace(tmp_path, self.jobs_file)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _now(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _zones_path(self, job_id: str) -> Path:
        return self.zones_dir / f"{job_id}.json"

    def create_job(self, job_id: str, video_path: str) -> Job:
        with self._lock:
            data = self._read_unlocked()
            job = {
                "id": job_id,
                "status": "uploaded",
                "video_path": video_path,
                "created_at": self._now(),
                "zones_path": str(self._zones_path(job_id)),
            "outputs": None,
            "metrics": None,
            "settings": {},
            "error": None,
            "logs": [],
        }
            data[job_id] = job
            self._write_unlocked(data)
            return Job(**job)

    def list_jobs(self) -> List[dict]:
        with self._lock:
            data = self._read_unlocked()
            return sorted(data.values(), key=lambda j: j.get("created_at", ""), reverse=True)

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            data = self._read_unlocked()
            return data.get(job_id)

    def update_job(self, job_id: str, **fields) -> None:
        with self._lock:
            data = self._read_unlocked()
            if job_id not in data:
                return
            data[job_id].update(fields)
            self._write_unlocked(data)

    def append_log(self, job_id: str, message: str) -> None:
        with self._lock:
            data = self._read_unlocked()
            job = data.get(job_id)
            if not job:
                return
            logs = job.get("logs") or []
            logs.append(f"{self._now()} {message}")
            job["logs"] = logs[-200:]
            data[job_id] = job
            self._write_unlocked(data)

    def update_progress(self, job_id: str, frame_processed: int, frame_total: int, fps: float) -> None:
        with self._lock:
            data = self._read_unlocked()
            job = data.get(job_id)
            if not job:
                return
            metrics = job.get("metrics") or {}
            metrics.update({
                "frame_processed": int(frame_processed),
                "frame_total": int(frame_total),
                "fps": float(fps),
                "updated_at": self._now(),
            })
            job["metrics"] = metrics
            data[job_id] = job
            self._write_unlocked(data)

    def set_zones(self, job_id: str, zones: dict) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        path = Path(job.get("zones_path") or self._zones_path(job_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(zones, indent=2), encoding="utf-8")
        self.update_job(job_id, zones_path=str(path))

    def get_zones(self, job_id: str) -> Optional[dict]:
        job = self.get_job(job_id)
        if not job:
            return None
        zones_path = job.get("zones_path")
        if zones_path and Path(zones_path).exists():
            return json.loads(Path(zones_path).read_text(encoding="utf-8"))
        if "zones" in job and job["zones"]:
            return job["zones"]
        return None

    def get_results(self, job_id: str) -> Optional[dict]:
        job = self.get_job(job_id)
        if not job:
            return None
        outputs = job.get("outputs") or {}
        results_url = outputs.get("results_json")
        if not results_url:
            return None
        if "/static/outputs/" in results_url:
            rel = results_url.split("/static/outputs/", 1)[1]
        else:
            rel = results_url
        results_path = (self.zones_dir.parent / "outputs" / Path(rel)).resolve()
        if results_path.exists():
            return json.loads(results_path.read_text(encoding="utf-8"))
        return None
