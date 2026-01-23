from __future__ import annotations

from pathlib import Path
from collections import defaultdict, deque
import json
import time

import cv2
import numpy as np
from ultralytics import YOLO


# -----------------------------
# Geometry helpers
# -----------------------------
def point_in_poly(pt, poly):
    """Ray casting point-in-polygon. poly = [[x,y], ...]"""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)):
            x_int = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
            if x < x_int:
                inside = not inside
    return inside


def draw_poly(img, poly, color, thickness=2):
    if not poly or len(poly) < 2:
        return
    pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(img, [pts], isClosed=True, color=color, thickness=thickness)


def put_label(img, text, x, y, color=(255, 255, 255), bg=(0, 0, 0)):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 2
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x1, y1 = max(0, x), max(0, y - th - 8)
    x2, y2 = min(img.shape[1], x + tw + 12), min(img.shape[0], y + 6)
    cv2.rectangle(img, (x1, y1), (x2, y2), bg, -1)
    cv2.putText(img, text, (x + 6, y - 5), font, scale, color, thickness, cv2.LINE_AA)


def safe_int(x, default=-1):
    try:
        return int(x)
    except Exception:
        return default


def normalize_zones(zones: dict | None) -> dict:
    """
    Expect format:
    {
      "entry": {"N":[[x,y],...], "S":..., "E":..., "W":...},
      "exit":  {"N":[[x,y],...], ...}
    }
    """
    base = {
        "entry": {"N": [], "S": [], "E": [], "W": []},
        "exit": {"N": [], "S": [], "E": [], "W": []},
    }
    if not zones:
        return base

    for t in ["entry", "exit"]:
        if t in zones and isinstance(zones[t], dict):
            for k in ["N", "S", "E", "W"]:
                poly = zones[t].get(k, [])
                if isinstance(poly, list):
                    # ensure list of [x,y]
                    clean = []
                    for p in poly:
                        if isinstance(p, (list, tuple)) and len(p) == 2:
                            clean.append([safe_int(p[0], 0), safe_int(p[1], 0)])
                    base[t][k] = clean
    return base


def find_zone(pt, zones_dict):
    """Return zone name if pt in any polygon"""
    for name, poly in zones_dict.items():
        if poly and len(poly) >= 3 and point_in_poly(pt, poly):
            return name
    return None


# -----------------------------
# Main processing
# -----------------------------
_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        # you can change to yolov8s.pt if you want more accuracy (slower on CPU)
        _MODEL = YOLO("yolov8n.pt")
    return _MODEL


def process_video(
    input_path: Path,
    outputs_dir: Path,
    job_id: str,
    zones: dict | None,
    max_frames: int = 600,
    min_exit_delay_frames: int = 5,
) -> dict:
    """
    Runs: YOLOv8 tracking + zones entry/exit + trajectories + heatmap
    Outputs:
      - overlay_mp4
      - heatmap_png
      - counts_json
    Returns dict with filenames (relative in /static/outputs).
    """

    outputs_dir.mkdir(parents=True, exist_ok=True)
    zones = normalize_zones(zones)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25.0

    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)

    overlay_name = f"{job_id}_overlay.mp4"
    heatmap_name = f"{job_id}_heatmap.png"
    counts_name = f"{job_id}_counts.json"

    overlay_path = outputs_dir / overlay_name
    heatmap_path = outputs_dir / heatmap_name
    counts_path = outputs_dir / counts_name

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(overlay_path), fourcc, fps, (W, H))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not open VideoWriter. Try installing opencv-python properly.")

    model = _get_model()

    # Vehicle class IDs in COCO: car=2, motorcycle=3, bus=5, truck=7
    vehicle_class_ids = {2, 3, 5, 7}

    # Tracking + OD
    track_entry = {}
    track_entry_frame = {}
    track_exit = {}
    track_counted = set()

    entry_counts = defaultdict(int)
    exit_counts = defaultdict(int)
    od_counts = defaultdict(int)

    # Trajectories: keep last N points per track
    paths = defaultdict(lambda: deque(maxlen=60))

    # Heatmap accumulator
    heat_accum = np.zeros((H, W), dtype=np.float32)

    total_frames = 0
    t0 = time.time()

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        total_frames += 1
        if total_frames > max_frames:
            break

        # YOLO track
        res_list = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            conf=0.25,
            iou=0.5,
            verbose=False,
            classes=list(vehicle_class_ids),
        )
        r = res_list[0] if res_list else None

        detections = []
        vehicles_now = 0

        if r is not None and getattr(r, "boxes", None) is not None and len(r.boxes) > 0:
            b = r.boxes
            xyxy = b.xyxy.cpu().numpy()
            cls = b.cls.cpu().numpy().astype(int)

            # ids can be None sometimes
            ids = None
            try:
                if b.id is not None:
                    ids = b.id.cpu().numpy()
            except Exception:
                ids = None

            for i in range(len(xyxy)):
                if int(cls[i]) not in vehicle_class_ids:
                    continue

                x1, y1, x2, y2 = xyxy[i]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                # "foot point" better for lane assignment
                zx, zy = cx, y2

                tid = -1
                if ids is not None:
                    tid = safe_int(ids[i], -1)

                vehicles_now += 1

                if tid != -1:
                    paths[tid].append((cx, cy))

                # heat accumulation
                cv2.circle(heat_accum, (cx, cy), 18, 1.0, -1)

                # zones
                entry = find_zone((zx, zy), zones["entry"])
                exit_ = find_zone((zx, zy), zones["exit"])

                if tid != -1 and entry and tid not in track_entry:
                    track_entry[tid] = entry
                    track_entry_frame[tid] = total_frames
                    entry_counts[entry] += 1

                if (
                    tid != -1
                    and tid in track_entry
                    and exit_
                    and tid not in track_exit
                    and (total_frames - track_entry_frame.get(tid, 0)) >= min_exit_delay_frames
                ):
                    track_exit[tid] = exit_
                    exit_counts[exit_] += 1

                if tid != -1 and tid in track_entry and tid in track_exit and tid not in track_counted:
                    k = (track_entry[tid], track_exit[tid])
                    od_counts[k] += 1
                    track_counted.add(tid)

                detections.append((x1, y1, x2, y2, tid))

        # ---- Draw overlay
        vis = frame.copy()

        # Draw zones (Entry blue, Exit red)
        for name, poly in zones["entry"].items():
            if poly and len(poly) >= 3:
                draw_poly(vis, poly, (255, 0, 0), 3)
                put_label(vis, f"Entry {name}", poly[0][0], poly[0][1] + 20, bg=(255, 0, 0))

        for name, poly in zones["exit"].items():
            if poly and len(poly) >= 3:
                draw_poly(vis, poly, (0, 0, 255), 3)
                put_label(vis, f"Exit {name}", poly[0][0], poly[0][1] + 20, bg=(0, 0, 255))

        # Draw trajectories (yellow)
        for tid, pts in paths.items():
            if len(pts) < 2:
                continue
            for j in range(1, len(pts)):
                cv2.line(vis, pts[j - 1], pts[j], (0, 255, 255), 2)

        # Draw detections + labels
        for (x1, y1, x2, y2, tid) in detections:
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 255), 2)
            if tid != -1:
                e = track_entry.get(tid)
                ex = track_exit.get(tid)
                if e or ex:
                    put_label(vis, f"#{tid} {e or '?'}->{ex or '?'}", x1, y1, color=(0, 0, 0), bg=(0, 255, 255))
                else:
                    put_label(vis, f"#{tid}", x1, y1, color=(0, 0, 0), bg=(0, 255, 255))

        # HUD
        total_od = int(sum(od_counts.values()))
        elapsed = max(1e-6, time.time() - t0)
        fps_now = total_frames / elapsed
        put_label(
            vis,
            f"Vehicles:{vehicles_now}  OD:{total_od}  FPS:{fps_now:.1f}  Frames:{total_frames}/{max_frames}",
            10,
            30,
            bg=(30, 30, 30),
        )

        writer.write(vis)

    # cleanup video io
    writer.release()
    cap.release()

    # ---- heatmap image
    heat = cv2.GaussianBlur(heat_accum, (0, 0), 15)
    heat_norm = cv2.normalize(heat, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heat_color = cv2.applyColorMap(heat_norm, cv2.COLORMAP_JET)

    # put heat on a black background (nicer export)
    cv2.imwrite(str(heatmap_path), heat_color)

    # ---- counts json
    out = {
        "job_id": job_id,
        "input": str(input_path.name),
        "max_frames": max_frames,
        "processed_frames": total_frames,
        "entry_counts": dict(entry_counts),
        "exit_counts": dict(exit_counts),
        "od_counts": {f"{k[0]}->{k[1]}": int(v) for k, v in od_counts.items()},
        "tracks": [
            {"id": int(tid), "entry": track_entry.get(tid), "exit": track_exit.get(tid)}
            for tid in sorted(set(list(track_entry.keys()) + list(track_exit.keys())))
        ],
    }
    counts_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    return {
        "overlay_mp4": overlay_name,
        "heatmap_png": heatmap_name,
        "counts_json": counts_name,
    }
