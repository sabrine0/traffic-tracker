# traffic_tracker

Traffic Tracker is a video analytics toolkit for traffic monitoring. It runs YOLOv8
on uploaded videos to detect and count road users, generate heatmaps, and export
zone-based summaries. A FastAPI web interface supports uploads, zone editing, and
results review.

## Tech stack

- Python 3.9+
- Ultralytics YOLOv8 (PyTorch)
- FastAPI + Jinja2
- OpenCV, NumPy, PyAV (optional utility)
- FFmpeg (optional, for MP4 optimization)

## Project structure

- `src/` - small utilities (e.g., video read test)
- `scripts/` - training helpers
- `traffic_web/` - FastAPI web app + templates

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi uvicorn[standard] opencv-python ultralytics numpy av python-multipart
```

Model weights are not included. Either place `yolov8n.pt` in the project root or
set `TRAFFIC_TRACKER_MODEL` to your custom weights:

```powershell
$env:TRAFFIC_TRACKER_MODEL = "C:\path\to\best.pt"
```

## Run the web app

```powershell
python -m uvicorn traffic_web.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

## Training (optional)

Prepare a YOLO-format dataset and a `data.yaml`, then run:

```powershell
python scripts/train_yolo.py --data data/traffic_data.yaml --model yolov8n.pt --epochs 50 --imgsz 640 --batch 8 --name traffic
```

The best weights are saved to `runs/detect/<name>/weights/best.pt`. Use
`--output` to copy them to a stable path.

## Inference utility (optional)

```powershell
python src/read_video.py "C:\path\to\video.mp4"
```

## Data policy

Datasets, labels, images, weights, and run outputs are intentionally excluded
from version control. Provide your own data and weights locally.
