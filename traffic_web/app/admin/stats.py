from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy.orm import Session

from ..db.models import Run


def _safe_json(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def compute_dashboard_stats(db: Session, owner_user_id: int | None = None) -> dict:
    query = db.query(Run).order_by(Run.created_at.desc())
    if owner_user_id is not None:
        query = query.filter(Run.owner_user_id == owner_user_id)
    runs = query.all()
    total_runs = len(runs)
    done_runs = len([r for r in runs if r.status == "done"])

    class_totals = defaultdict(int)
    entry_totals = defaultdict(int)
    exit_totals = defaultdict(int)
    od_totals = defaultdict(int)

    total_persons = 0
    total_vehicles = 0
    total_flow = 0
    total_duration = 0.0

    detections_total = 0
    detections_with_id = 0
    conf_weighted_sum = 0.0
    conf_weight = 0

    entry_minute_bins = defaultdict(int)

    for run in runs:
        metrics = _safe_json(run.metrics_json)
        if not metrics:
            continue

        class_counts = metrics.get("class_counts", {})
        if isinstance(class_counts, dict):
            for k, v in class_counts.items():
                try:
                    class_totals[str(k)] += int(v)
                except Exception:
                    continue

            persons = int(class_counts.get("person", 0) or 0)
            total_persons += persons
            total_vehicles += sum(
                int(v) for k, v in class_counts.items() if str(k) != "person"
            )

        entry_counts = metrics.get("entry_counts", {})
        if isinstance(entry_counts, dict):
            for k, v in entry_counts.items():
                try:
                    entry_totals[str(k)] += int(v)
                    total_flow += int(v)
                except Exception:
                    continue

        exit_counts = metrics.get("exit_counts", {})
        if isinstance(exit_counts, dict):
            for k, v in exit_counts.items():
                try:
                    exit_totals[str(k)] += int(v)
                except Exception:
                    continue

        od_counts = metrics.get("od_counts", {})
        if isinstance(od_counts, dict):
            for k, v in od_counts.items():
                try:
                    od_totals[str(k)] += int(v)
                except Exception:
                    continue

        fps = metrics.get("fps") or 0
        duration = metrics.get("duration_sec")
        if duration is None:
            frame_count = metrics.get("frame_count") or 0
            if fps:
                duration = float(frame_count) / float(fps)
        if duration:
            total_duration += float(duration)

        tracks = metrics.get("tracks", [])
        if fps and isinstance(tracks, list):
            for t in tracks:
                if not isinstance(t, dict):
                    continue
                entry_frame = t.get("entry_frame")
                if entry_frame is None:
                    continue
                try:
                    minute = int((float(entry_frame) / float(fps)) // 60)
                except Exception:
                    continue
                entry_minute_bins[minute] += 1

        quality = metrics.get("quality", {})
        if isinstance(quality, dict):
            detections_total += int(quality.get("detections_total", 0) or 0)
            detections_with_id += int(quality.get("detections_with_id", 0) or 0)
            avg_conf = quality.get("avg_confidence")
            conf_count = int(quality.get("confidence_count", 0) or 0)
            if avg_conf is not None and conf_count:
                conf_weighted_sum += float(avg_conf) * conf_count
                conf_weight += conf_count

    flow_per_min = 0.0
    flow_per_hour = 0.0
    if total_duration > 0:
        flow_per_min = total_flow / (total_duration / 60.0)
        flow_per_hour = total_flow / (total_duration / 3600.0)

    peak_period = None
    if entry_minute_bins:
        peak_minute = max(entry_minute_bins.items(), key=lambda x: x[1])[0]
        peak_count = entry_minute_bins[peak_minute]
        peak_period = {
            "label": f"Minute {peak_minute}–{peak_minute + 1}",
            "count": peak_count,
        }

    od_total = sum(od_totals.values())
    dominant_direction = None
    if od_totals:
        top_od = max(od_totals.items(), key=lambda x: x[1])
        dominant_direction = {
            "pair": top_od[0],
            "count": int(top_od[1]),
            "share": (float(top_od[1]) / float(od_total)) if od_total else 0.0,
        }

    avg_confidence = None
    if conf_weight:
        avg_confidence = conf_weighted_sum / conf_weight

    lost_id_rate = None
    if detections_total:
        lost_id_rate = 1.0 - (float(detections_with_id) / float(detections_total))

    class_rows = [{"class": k, "count": v} for k, v in sorted(class_totals.items(), key=lambda x: x[1], reverse=True)]
    entry_rows = [{"zone": k, "count": v} for k, v in sorted(entry_totals.items(), key=lambda x: x[1], reverse=True)]
    exit_rows = [{"zone": k, "count": v} for k, v in sorted(exit_totals.items(), key=lambda x: x[1], reverse=True)]
    od_rows = [{"flow": k, "count": v} for k, v in sorted(od_totals.items(), key=lambda x: x[1], reverse=True)][:20]

    return {
        "totals": {
            "runs_total": total_runs,
            "runs_done": done_runs,
            "total_persons": total_persons,
            "total_vehicles": total_vehicles,
        },
        "counts": {
            "classes": class_rows,
            "entries": entry_rows,
            "exits": exit_rows,
            "od": od_rows,
        },
        "kpis": {
            "flow_per_min": flow_per_min,
            "flow_per_hour": flow_per_hour,
            "peak_period": peak_period,
            "dominant_direction": dominant_direction,
        },
        "quality": {
            "avg_confidence": avg_confidence,
            "lost_id_rate": lost_id_rate,
            "detections_total": detections_total,
        },
    }
