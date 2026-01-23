from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLOv8 on a custom traffic dataset."
    )
    parser.add_argument("--data", required=True, help="Path to data.yaml")
    parser.add_argument(
        "--model",
        default="yolov8n.pt",
        help="Base model or weights path (default: yolov8n.pt)",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--project", default="runs/detect")
    parser.add_argument("--name", default="traffic")
    parser.add_argument("--device", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to copy best.pt after training",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"data.yaml not found: {data_path}")

    model = YOLO(str(args.model))
    train_kwargs = {
        "data": str(data_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "project": args.project,
        "name": args.name,
    }
    if args.device:
        train_kwargs["device"] = args.device

    model.train(**train_kwargs)

    best_path = Path(args.project) / args.name / "weights" / "best.pt"
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if best_path.exists():
            shutil.copy2(best_path, out_path)
            print(f"Copied best weights to {out_path}")
        else:
            print(f"Best weights not found at {best_path}")
    else:
        print(f"Best weights: {best_path}")


if __name__ == "__main__":
    main()
