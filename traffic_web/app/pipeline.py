# traffic_web/app/pipeline.py
from __future__ import annotations
from pathlib import Path
import json
import time
import subprocess
from collections import defaultdict, deque
import cv2
import numpy as np
from ultralytics import YOLO
from .xlsx_writer import write_xlsx
VEHICLE_CLASS_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck (COCO)
DEFAULT_ZONE_LABELS = [f"V{i}" for i in range(1, 14)] + [f"P{i}" for i in range(1, 14)]
def _model_name_map(model):
    names = getattr(model, "names", None)
    if not names:
        return {}
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    return {int(i): str(v) for i, v in enumerate(names)}

def _resolve_class_ids(model, class_names, class_ids):
    name_map = _model_name_map(model)
    if class_names:
        name_to_id = {str(v).lower(): int(k) for k, v in name_map.items()}
        missing = []
        resolved = []
        for name in class_names:
            key = str(name).lower()
            if key in name_to_id:
                resolved.append(name_to_id[key])
            else:
                missing.append(str(name))
        if missing and name_to_id:
            raise RuntimeError(
                f"Classes not found in model.names: {', '.join(missing)}"
            )
        if resolved:
            return resolved
    if class_ids:
        return list(class_ids)
    return list(VEHICLE_CLASS_IDS)
def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_int = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
            if x < x_int:
                inside = not inside
    return inside
def draw_poly(img, poly, color, thickness=2):
    if not poly or len(poly) < 2:
        return
    pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(img, [pts], isClosed=True, color=color, thickness=thickness)
def put_label(img, text, x, y, bg=(0, 0, 0), fg=(255, 255, 255)):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 2
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x1, y1 = max(0, x), max(0, y - th - 8)
    x2, y2 = min(img.shape[1], x + tw + 10), min(img.shape[0], y + 6)
    cv2.rectangle(img, (x1, y1), (x2, y2), bg, -1)
    cv2.putText(img, text, (x + 5, y - 5), font, scale, fg, thickness, cv2.LINE_AA)
def _finalize_video(raw_path: Path, final_path: Path) -> bool:
    if not raw_path.exists():
        return False
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(raw_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(final_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0 or not final_path.exists():
            raw_path.replace(final_path)
        else:
            raw_path.unlink()
        return True
    except FileNotFoundError:
        raw_path.replace(final_path)
        return True
    except Exception:
        if final_path.exists():
            final_path.unlink()
        raw_path.replace(final_path)
        return True
def normalize_zones(zones: dict | None, labels: list[str] | None = None) -> dict:
    labels = []
    fallback_labels = labels if labels else DEFAULT_ZONE_LABELS[:]
    if isinstance(zones, dict):
        for t in ["entry", "exit"]:
            zdict = zones.get(t)
            if isinstance(zdict, dict):
                for k in zdict.keys():
                    name = str(k)
                    if name not in labels:
                        labels.append(name)
    if not labels:
        labels = fallback_labels[:]
    base = {"entry": {k: [] for k in labels}, "exit": {k: [] for k in labels}}
    if not zones or not isinstance(zones, dict):
        return base
    for t in ["entry", "exit"]:
        zdict = zones.get(t)
        if not isinstance(zdict, dict):
            continue
        for name, poly in zdict.items():
            name = str(name)
            if name not in base[t]:
                base[t][name] = []
            if not isinstance(poly, list):
                continue
            clean = []
            for p in poly:
                if isinstance(p, (list, tuple)) and len(p) == 2:
                    try:
                        clean.append([int(p[0]), int(p[1])])
                    except Exception:
                        continue
            base[t][name] = clean
    for name in list(base["entry"].keys()):
        base["exit"].setdefault(name, [])
    for name in list(base["exit"].keys()):
        base["entry"].setdefault(name, [])
    return base
def scale_zones(zones: dict, scale: float) -> dict:
    if scale == 1.0:
        return zones
    scaled = {"entry": {}, "exit": {}}
    for t in ["entry", "exit"]:
        for name, poly in zones[t].items():
            scaled[t][name] = [[int(round(x * scale)), int(round(y * scale))] for x, y in poly]
    return scaled
def check_zone(pt, zones_dict):
    for name, poly in zones_dict.items():
        if poly and len(poly) >= 3 and point_in_poly(pt, poly):
            return name
    return None
def _zone_names(zones, entry_counts, exit_counts, od_counts, default_labels=None):
    names = []
    base_labels = default_labels if default_labels else DEFAULT_ZONE_LABELS[:]
    def add(name):
        if name and name not in names:
            names.append(name)
    if isinstance(zones, dict):
        for t in ["entry", "exit"]:
            zdict = zones.get(t)
            if isinstance(zdict, dict):
                for k in zdict.keys():
                    add(str(k))
    for k in entry_counts.keys():
        add(str(k))
    for k in exit_counts.keys():
        add(str(k))
    for k in od_counts.keys():
        if isinstance(k, (list, tuple)) and len(k) == 2:
            add(str(k[0]))
            add(str(k[1]))
        elif isinstance(k, str) and "->" in k:
            a, b = k.split("->", 1)
            add(a)
            add(b)
    if not names:
        names = base_labels[:]
    ordered = [z for z in base_labels if z in names]
    for z in names:
        if z not in ordered:
            ordered.append(z)
    return ordered
def _letter_zone_map(names):
    if not names:
        return {}
    letter_map = {chr(i): f"V{i - ord('A') + 1}" for i in range(ord("A"), ord("M") + 1)}
    as_str = [str(n) for n in names]
    if not all(n in letter_map for n in as_str):
        return {}
    return {n: letter_map[n] for n in as_str}
def _remap_counts(counts, zone_map):
    remapped = defaultdict(int)
    for k, v in counts.items():
        name = zone_map.get(str(k), str(k))
        remapped[name] += int(v)
    return remapped
def _remap_od_counts(od_counts, zone_map):
    remapped = defaultdict(int)
    for k, v in od_counts.items():
        if isinstance(k, (list, tuple)) and len(k) == 2:
            entry, exit_ = k
        elif isinstance(k, str) and "->" in k:
            entry, exit_ = k.split("->", 1)
        else:
            continue
        entry = zone_map.get(str(entry), str(entry))
        exit_ = zone_map.get(str(exit_), str(exit_))
        remapped[(entry, exit_)] += int(v)
    return remapped


def _zone_allows_class(zone_name, class_name):
    if not zone_name:
        return False
    prefix = str(zone_name).upper()[:1]
    cname = str(class_name).lower() if class_name is not None else None
    if prefix == "P":
        return cname == "person"
    if prefix == "V":
        return cname is None or cname != "person"
    return True
def process_video(
    video_path: str,
    zones: dict,
    out_dir: Path,
    job_id: str,
    model_path: Path,
    conf: float = 0.25,
    iou: float = 0.5,
    max_width: int = 1280,
    min_exit_delay_frames: int = 5,
    class_ids: list[int] | None = None,
    class_names: list[str] | None = None,
    device: str | None = None,
    zone_labels: list[str] | None = None,
    progress_cb=None,
):
    """
    Outputs:
      - {job_id}/overlay.mp4
      - {job_id}/heatmap.png
      - {job_id}/results.json
      - {job_id}/report.xlsx
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    job_dir = out_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = job_dir / "overlay.mp4"
    overlay_raw_path = job_dir / "overlay_raw.mp4"
    heatmap_path = job_dir / "heatmap.png"
    heatmap_video_path = job_dir / "heatmap_video.mp4"
    heatmap_video_raw_path = job_dir / "heatmap_video_raw.mp4"
    results_path = job_dir / "results.json"
    report_path = job_dir / "report.xlsx"
    zone_labels = zone_labels or DEFAULT_ZONE_LABELS[:]
    zones = normalize_zones(zones, labels=zone_labels)
    if not model_path.exists():
        raise RuntimeError(f"Model not found: {model_path}")
    model = YOLO(str(model_path))
    class_ids = _resolve_class_ids(model, class_names, class_ids)
    model_name_map = _model_name_map(model)
    if model_name_map:
        class_id_to_name = model_name_map
    else:
        class_id_to_name = {cid: str(cid) for cid in class_ids}
        if class_names:
            for cid, name in zip(class_ids, class_names):
                class_id_to_name[cid] = str(name)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if progress_cb:
        progress_cb(0, total_frames, fps)
    last_report = time.time()
    w0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h0 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = 1.0
    if w0 > max_width:
        scale = max_width / float(w0)
    out_w = int(w0 * scale)
    out_h = int(h0 * scale)
    zones_scaled = scale_zones(zones, scale)
    entry_zones = zones_scaled.get("entry", {})
    exit_zones = zones_scaled.get("exit", {})
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(overlay_raw_path), fourcc, fps, (out_w, out_h))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not open VideoWriter. Check your OpenCV install.")
    heatmap_writer = cv2.VideoWriter(str(heatmap_video_raw_path), fourcc, fps, (out_w, out_h))
    if not heatmap_writer.isOpened():
        heatmap_writer.release()
        heatmap_writer = None
    traj = defaultdict(lambda: deque(maxlen=60))
    heat_accum = np.zeros((out_h, out_w), dtype=np.float32)
    heat_vis = None
    heat_stride = 5
    base_frame = None
    track_entry = {}
    track_entry_frame = {}
    track_exit_armed = {}
    track_exit = {}
    track_exit_frame = {}
    track_counted = set()
    track_first_frame = {}
    track_last_frame = {}
    track_class = {}
    class_counts = defaultdict(int)
    entry_counts = defaultdict(int)
    exit_counts = defaultdict(int)
    od_counts = defaultdict(int)
    detections_total = 0
    detections_with_id = 0
    confidence_sum = 0.0
    confidence_count = 0
    frame_i = 0
    start_time = time.time()
    track_kwargs = {
        "persist": True,
        "tracker": "bytetrack.yaml",
        "conf": conf,
        "iou": iou,
        "verbose": False,
        "classes": class_ids,
    }
    if device:
        track_kwargs["device"] = device
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frame_i += 1
        if scale != 1.0:
            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
        if base_frame is None:
            base_frame = frame.copy()
        res_list = model.track(frame, **track_kwargs)
        res = res_list[0] if res_list else None
        vis = frame.copy()
        for name, poly in entry_zones.items():
            if poly and len(poly) >= 3:
                draw_poly(vis, poly, (255, 0, 0), 3)
                put_label(vis, f"Entry {name}", int(poly[0][0]), int(poly[0][1]) + 20, bg=(255, 0, 0), fg=(0, 0, 0))
        for name, poly in exit_zones.items():
            if poly and len(poly) >= 3:
                draw_poly(vis, poly, (0, 0, 255), 3)
                put_label(vis, f"Exit {name}", int(poly[0][0]), int(poly[0][1]) + 20, bg=(0, 0, 255), fg=(255, 255, 255))
        if res is not None and res.boxes is not None and len(res.boxes) > 0:
            b = res.boxes
            xyxy = b.xyxy.cpu().numpy()
            cls = None
            try:
                if b.cls is not None:
                    cls = b.cls.cpu().numpy().astype(int)
            except Exception:
                cls = None
            conf = None
            try:
                if b.conf is not None:
                    conf = b.conf.cpu().numpy().astype(float)
            except Exception:
                conf = None
            ids = None
            if b.id is not None:
                try:
                    ids = b.id.cpu().numpy().astype(int)
                except Exception:
                    ids = None
            for i in range(len(xyxy)):
                x1, y1, x2, y2 = xyxy[i].astype(int)
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                foot = (cx, y2)
                class_id = int(cls[i]) if cls is not None else None
                class_name = None
                if class_id is not None:
                    class_name = str(class_id_to_name.get(class_id, class_id)).lower()
                detections_total += 1
                if conf is not None and i < len(conf):
                    confidence_sum += float(conf[i])
                    confidence_count += 1
                tid = int(ids[i]) if ids is not None else -1
                if tid != -1:
                    detections_with_id += 1
                    traj[tid].append((cx, cy))
                    if tid not in track_first_frame:
                        track_first_frame[tid] = frame_i
                    track_last_frame[tid] = frame_i
                    if class_name is not None and tid not in track_class:
                        track_class[tid] = class_name
                        class_counts[class_name] += 1
                if tid != -1 and class_name is None:
                    class_name = track_class.get(tid)
                cv2.circle(heat_accum, (cx, cy), 18, 1.0, -1)
                entry = check_zone(foot, entry_zones)
                exit_ = check_zone(foot, exit_zones)
                if tid != -1 and entry and tid not in track_entry and _zone_allows_class(entry, class_name):
                    track_entry[tid] = entry
                    track_entry_frame[tid] = frame_i
                    # Arm exit only after the track leaves all exit zones once.
                    # This prevents instant false exits when entry/exit zones overlap.
                    track_exit_armed[tid] = False
                    entry_counts[entry] += 1
                if tid != -1 and tid in track_entry and tid not in track_exit and not exit_:
                    track_exit_armed[tid] = True
                if (
                    tid != -1
                    and tid in track_entry
                    and exit_
                    and tid not in track_exit
                    and track_exit_armed.get(tid, False)
                    and _zone_allows_class(exit_, class_name)
                    and (frame_i - track_entry_frame.get(tid, 0)) >= min_exit_delay_frames
                ):
                    track_exit[tid] = exit_
                    track_exit_frame[tid] = frame_i
                    exit_counts[exit_] += 1
                if tid != -1 and tid in track_entry and tid in track_exit and tid not in track_counted:
                    od_counts[(track_entry[tid], track_exit[tid])] += 1
                    track_counted.add(tid)
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 255), 2)
                if tid != -1:
                    e = track_entry.get(tid) or entry or "?"
                    x = track_exit.get(tid) or exit_ or "?"
                    put_label(vis, f"#{tid} {e}->{x}", x1, y1, bg=(0, 255, 255), fg=(0, 0, 0))
        for tid, pts in traj.items():
            if len(pts) < 2:
                continue
            for j in range(1, len(pts)):
                cv2.line(vis, pts[j - 1], pts[j], (0, 255, 255), 2)
        if heatmap_writer is not None:
            if heat_vis is None or (frame_i % heat_stride == 0):
                heat = cv2.GaussianBlur(heat_accum, (0, 0), 15)
                heat_norm = cv2.normalize(heat, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                heat_color = cv2.applyColorMap(heat_norm, cv2.COLORMAP_JET)
                if base_frame is not None and base_frame.shape == heat_color.shape:
                    heat_vis = cv2.addWeighted(base_frame, 0.45, heat_color, 0.55, 0)
                else:
                    heat_vis = heat_color
            heatmap_writer.write(heat_vis)
        writer.write(vis)
        if progress_cb and (frame_i % 50 == 0 or time.time() - last_report >= 1):
            progress_cb(frame_i, total_frames, fps)
            last_report = time.time()
    cap.release()
    writer.release()
    if heatmap_writer is not None:
        heatmap_writer.release()
    _finalize_video(overlay_raw_path, overlay_path)
    if heatmap_video_raw_path.exists():
        _finalize_video(heatmap_video_raw_path, heatmap_video_path)
    if progress_cb:
        progress_cb(frame_i, total_frames, fps)
    heat = cv2.GaussianBlur(heat_accum, (0, 0), 15)
    heat_norm = cv2.normalize(heat, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heat_color = cv2.applyColorMap(heat_norm, cv2.COLORMAP_JET)
    if base_frame is not None and base_frame.shape == heat_color.shape:
        heat_out = cv2.addWeighted(base_frame, 0.45, heat_color, 0.55, 0)
    else:
        heat_out = heat_color
    cv2.imwrite(str(heatmap_path), heat_out)
    tracks = []
    for tid in sorted(set(list(track_first_frame.keys()) + list(track_last_frame.keys()))):
        tracks.append(
            {
                "id": int(tid),
                "entry": track_entry.get(tid),
                "exit": track_exit.get(tid),
                "class": track_class.get(tid),
                "first_frame": track_first_frame.get(tid, 0),
                "last_frame": track_last_frame.get(tid, 0),
                "entry_frame": track_entry_frame.get(tid),
                "exit_frame": track_exit_frame.get(tid),
            }
        )
    zone_names = _zone_names(zones, entry_counts, exit_counts, od_counts, zone_labels)
    zone_map = _letter_zone_map(zone_names)
    if zone_map:
        entry_counts = _remap_counts(entry_counts, zone_map)
        exit_counts = _remap_counts(exit_counts, zone_map)
        od_counts = _remap_od_counts(od_counts, zone_map)
        for tid, name in list(track_entry.items()):
            if name is not None:
                track_entry[tid] = zone_map.get(str(name), str(name))
        for tid, name in list(track_exit.items()):
            if name is not None:
                track_exit[tid] = zone_map.get(str(name), str(name))
        zone_names = [zone_map.get(str(z), str(z)) for z in zone_names]
    results_payload = {
        "job_id": job_id,
        "video": Path(video_path).name,
        "frame_count": frame_i,
        "fps": fps,
        "duration_sec": round(frame_i / fps, 2) if fps else 0,
        "entry_counts": dict(entry_counts),
        "exit_counts": dict(exit_counts),
        "od_counts": {f"{k[0]}->{k[1]}": int(v) for k, v in od_counts.items()},
        "tracks": tracks,
        "zone_names": zone_names,
        "classes": class_names or [str(cid) for cid in class_ids],
        "class_counts": dict(class_counts),
        "quality": {
            "detections_total": int(detections_total),
            "detections_with_id": int(detections_with_id),
            "lost_id_rate": (
                1.0 - (float(detections_with_id) / float(detections_total))
                if detections_total
                else None
            ),
            "avg_confidence": (
                float(confidence_sum) / float(confidence_count)
                if confidence_count
                else None
            ),
            "confidence_count": int(confidence_count),
        },
        "files": {
            "overlay_video": overlay_path.name,
            "heatmap_image": heatmap_path.name,
            "heatmap_video": heatmap_video_path.name if heatmap_video_path.exists() else None,
            "results_json": results_path.name,
            "report_xlsx": report_path.name,
        },
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(time.time() - start_time, 2),
    }
    results_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    counts_rows = [["Zone", "Entry Count", "Exit Count"]]
    for z in zone_names:
        counts_rows.append([z, int(entry_counts.get(z, 0)), int(exit_counts.get(z, 0))])
    od_header = ["Entry / Exit"] + zone_names
    od_rows = [od_header]
    for entry in zone_names:
        row = [entry]
        for exit_ in zone_names:
            row.append(int(od_counts.get((entry, exit_), 0)))
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
        ["Overlay Video", overlay_path.name],
        ["Heatmap", heatmap_path.name],
        ["Heatmap Video", heatmap_video_path.name if heatmap_video_path.exists() else ""],
        ["Results JSON", results_path.name],
        ["Report XLSX", report_path.name],
    ]
    summary_rows = [
        ["Job ID", job_id],
        ["Video", Path(video_path).name],
        ["Frames", frame_i],
        ["FPS", round(fps, 2)],
        ["Duration (sec)", round(frame_i / fps, 2) if fps else 0],
        ["Tracks", len(tracks)],
        ["OD Flows", int(sum(od_counts.values()))],
        ["Classes", ", ".join(class_names or [str(cid) for cid in class_ids])],
    ]
    write_xlsx(
        report_path,
        [
            ("Summary", summary_rows),
            ("Counts by Zone", counts_rows),
            ("OD Matrix", od_rows),
            ("Tracks", tracks_rows),
            ("Files", files_rows),
        ],
    )
    outputs = {
        "overlay_video": str(overlay_path.relative_to(out_dir)).replace("\\", "/"),
        "heatmap": str(heatmap_path.relative_to(out_dir)).replace("\\", "/"),
        "heatmap_video": (
            str(heatmap_video_path.relative_to(out_dir)).replace("\\", "/")
            if heatmap_video_path.exists()
            else None
        ),
        "results_json": str(results_path.relative_to(out_dir)).replace("\\", "/"),
        "report_xlsx": str(report_path.relative_to(out_dir)).replace("\\", "/"),
    }
    metrics = {
        "entry_counts": dict(entry_counts),
        "exit_counts": dict(exit_counts),
        "od_counts": {f"{k[0]}->{k[1]}": int(v) for k, v in od_counts.items()},
        "tracks": tracks,
        "frame_count": frame_i,
        "fps": fps,
        "zone_names": zone_names,
        "classes": class_names or [str(cid) for cid in class_ids],
        "class_counts": dict(class_counts),
        "quality": {
            "detections_total": int(detections_total),
            "detections_with_id": int(detections_with_id),
            "lost_id_rate": (
                1.0 - (float(detections_with_id) / float(detections_total))
                if detections_total
                else None
            ),
            "avg_confidence": (
                float(confidence_sum) / float(confidence_count)
                if confidence_count
                else None
            ),
            "confidence_count": int(confidence_count),
        },
    }
    return outputs, metrics
