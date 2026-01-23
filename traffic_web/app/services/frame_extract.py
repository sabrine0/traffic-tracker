# traffic_web/app/services/frame_extract.py
from __future__ import annotations
from pathlib import Path
import av
from PIL import Image


def extract_first_frame(input_path: Path, out_path: Path) -> dict:
    """
    Extract first frame as PNG to out_path.
    Returns width/height.
    """
    container = av.open(str(input_path))
    video_stream = next((s for s in container.streams if s.type == "video"), None)
    if video_stream is None:
        container.close()
        raise RuntimeError("No video stream found.")

    width = video_stream.codec_context.width
    height = video_stream.codec_context.height

    frame = next(container.decode(video=video_stream.index), None)
    if frame is None:
        container.close()
        raise RuntimeError("Could not decode first frame.")

    rgb = frame.to_ndarray(format="rgb24")
    img = Image.fromarray(rgb)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)

    container.close()
    return {"width": width, "height": height}
