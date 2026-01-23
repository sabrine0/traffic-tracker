# src/read_video.py
# Reads a video file or RTSP stream with PyAV (FFmpeg) WITHOUT OpenCV.
# Prints stream info and reads a few frames to confirm everything works.

from __future__ import annotations

import sys
from pathlib import Path
import av


def read_video_info(source: str, max_frames: int = 50) -> None:
    print(f"[INFO] Opening source: {source}")

    # Open container (file path or rtsp url)
    container = av.open(source)

    # Get first video stream
    video_stream = next((s for s in container.streams if s.type == "video"), None)
    if video_stream is None:
        container.close()
        raise RuntimeError("No video stream found in the source.")

    fps = float(video_stream.average_rate) if video_stream.average_rate else None
    width = video_stream.codec_context.width
    height = video_stream.codec_context.height
    codec = video_stream.codec_context.name

    print(f"[INFO] Stream: {width}x{height}, fps={fps}, codec={codec}")

    count = 0
    for frame in container.decode(video=video_stream.index):
        # Convert to numpy RGB array (needed later for YOLO)
        img = frame.to_ndarray(format="rgb24")
        count += 1

        if count == 1:
            print(f"[INFO] First frame shape: {img.shape} (H,W,C)")

        if count >= max_frames:
            break

    container.close()
    print(f"[DONE] Read {count} frames successfully.")


def print_usage() -> None:
    print(
        "\nUSAGE:\n"
        "  1) Put a video at: data/videos/test.mp4 then run:\n"
        "     python src/read_video.py\n\n"
        "  2) Or run with an explicit path:\n"
        '     python src/read_video.py "C:\\path\\to\\video.mp4"\n\n'
        "  3) Or RTSP:\n"
        '     python src/read_video.py "rtsp://user:pass@ip:554/stream"\n'
    )


if __name__ == "__main__":
    # Default path inside project
    default_video = Path("data/videos/test.mp4")

    # If user gave an argument, use it; otherwise use default
    if len(sys.argv) > 1:
        source = sys.argv[1]
    else:
        source = str(default_video)

    # Helpful message if default file not found
    if source == str(default_video) and not default_video.exists():
        print("[ERROR] Video not found at data/videos/test.mp4")
        print_usage()
        sys.exit(1)

    # Run test read
    read_video_info(source, max_frames=50)
