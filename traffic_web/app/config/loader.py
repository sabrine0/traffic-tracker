from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any, Dict


_CONFIG_DIR = Path(__file__).resolve().parent
_DEFAULTS_PATH = _CONFIG_DIR / "defaults.json"


_SAFE_DEFAULTS: Dict[str, Any] = {
    "model": {
        "path": None,
        "default_name": "yolov8n.pt",
        "device_default": "auto",
    },
    "classes": {
        "order": ["person", "bicycle", "car", "motorcycle", "bus", "truck"],
        "options": {
            "person": {"id": 0, "label": "Person"},
            "bicycle": {"id": 1, "label": "Bicycle"},
            "car": {"id": 2, "label": "Car"},
            "motorcycle": {"id": 3, "label": "Motorcycle"},
            "bus": {"id": 5, "label": "Bus"},
            "truck": {"id": 7, "label": "Truck"},
        },
        "default": ["car", "motorcycle", "bus", "truck", "person"],
    },
    "zones": {
        "labels": [f"V{i}" for i in range(1, 14)] + [f"P{i}" for i in range(1, 14)],
    },
    "tracking": {
        "conf": 0.25,
        "iou": 0.5,
        "min_exit_delay_frames": 5,
    },
    "video": {
        "max_width": 1280,
    },
    "analysis": {
        "heatmap_enabled": True,
        "od_enabled": True,
    },
}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(override, dict):
        return base
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_config(cfg: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(cfg)

    classes = out.get("classes")
    if not isinstance(classes, dict):
        classes = dict(defaults["classes"])
    else:
        classes = dict(classes)
    options = classes.get("options")
    if not isinstance(options, dict) or not options:
        options = dict(defaults["classes"]["options"])
    order = classes.get("order")
    if not isinstance(order, list) or not order:
        order = list(defaults["classes"]["order"])
    default_list = classes.get("default")
    if not isinstance(default_list, list) or not default_list:
        default_list = list(defaults["classes"]["default"])
    order = [str(k) for k in order if str(k) in options]
    if not order:
        order = list(defaults["classes"]["order"])
    default_list = [str(k) for k in default_list if str(k) in options]
    if not default_list:
        default_list = list(defaults["classes"]["default"])
    classes["options"] = options
    classes["order"] = order
    classes["default"] = default_list
    out["classes"] = classes

    zones = out.get("zones")
    if not isinstance(zones, dict):
        zones = dict(defaults["zones"])
    else:
        zones = dict(zones)
    labels = zones.get("labels")
    if not isinstance(labels, list) or not labels:
        labels = list(defaults["zones"]["labels"])
    zones["labels"] = [str(x) for x in labels if str(x)]
    if not zones["labels"]:
        zones["labels"] = list(defaults["zones"]["labels"])
    out["zones"] = zones

    tracking = out.get("tracking")
    if not isinstance(tracking, dict):
        tracking = dict(defaults["tracking"])
    else:
        tracking = dict(tracking)
    conf = tracking.get("conf")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        tracking["conf"] = defaults["tracking"]["conf"]
    iou = tracking.get("iou")
    if not isinstance(iou, (int, float)) or iou < 0 or iou > 1:
        tracking["iou"] = defaults["tracking"]["iou"]
    min_exit = tracking.get("min_exit_delay_frames")
    if not isinstance(min_exit, int) or min_exit < 0:
        tracking["min_exit_delay_frames"] = defaults["tracking"]["min_exit_delay_frames"]
    out["tracking"] = tracking

    video = out.get("video")
    if not isinstance(video, dict):
        video = dict(defaults["video"])
    else:
        video = dict(video)
    max_width = video.get("max_width")
    if not isinstance(max_width, int) or max_width <= 0:
        video["max_width"] = defaults["video"]["max_width"]
    out["video"] = video

    model = out.get("model")
    if not isinstance(model, dict):
        model = dict(defaults["model"])
    else:
        model = dict(model)
    if "path" in model and model["path"] is not None and not isinstance(model["path"], str):
        model["path"] = defaults["model"]["path"]
    if not isinstance(model.get("default_name"), str) or not model.get("default_name"):
        model["default_name"] = defaults["model"]["default_name"]
    device_default = model.get("device_default")
    if not isinstance(device_default, str) or not device_default:
        model["device_default"] = defaults["model"]["device_default"]
    out["model"] = model

    analysis = out.get("analysis")
    if not isinstance(analysis, dict):
        analysis = dict(defaults["analysis"])
    else:
        analysis = dict(analysis)
    out["analysis"] = analysis

    return out


def load_config() -> Dict[str, Any]:
    defaults = _read_json(_DEFAULTS_PATH)
    if not defaults:
        defaults = dict(_SAFE_DEFAULTS)
    else:
        defaults = _merge(_SAFE_DEFAULTS, defaults)

    override_path = os.getenv("TRAFFIC_TRACKER_CONFIG")
    overrides: Dict[str, Any] = {}
    if override_path:
        path = Path(override_path).expanduser()
        if not path.is_absolute():
            path = (_CONFIG_DIR / path).resolve()
        overrides = _read_json(path)
    else:
        local_path = _CONFIG_DIR / "local.json"
        if local_path.exists():
            overrides = _read_json(local_path)

    merged = _merge(defaults, overrides)
    return _validate_config(merged, defaults)


def resolve_model_path(app_dir: Path, config: Dict[str, Any]) -> Path:
    env_path = os.getenv("TRAFFIC_TRACKER_MODEL")
    if env_path:
        model_path = Path(env_path).expanduser()
    else:
        model_cfg = config.get("model", {})
        cfg_path = model_cfg.get("path") or model_cfg.get("default_name") or "yolov8n.pt"
        model_path = Path(str(cfg_path)).expanduser()

    if not model_path.is_absolute():
        project_root = app_dir.parent.parent
        model_path = (project_root / model_path).resolve()
    return model_path
