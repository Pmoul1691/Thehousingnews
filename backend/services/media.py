"""Media utilities: ffprobe for video metadata + ffmpeg for thumbnail extraction."""
import subprocess
import tempfile
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def probe_video(data: bytes) -> dict:
    """Run ffprobe over an in-memory video. Returns {duration_s, width, height}.
    Raises ValueError if ffprobe fails or the file is not a parseable video."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(data)
        path = f.name
    try:
        cmd = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        if result.returncode != 0:
            raise ValueError(f"ffprobe failed: {result.stderr.decode(errors='ignore')[:200]}")
        info = json.loads(result.stdout.decode())
        fmt = info.get("format", {})
        duration = float(fmt.get("duration") or 0)
        width = 0
        height = 0
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                width = int(s.get("width") or 0)
                height = int(s.get("height") or 0)
                break
        return {"duration_s": duration, "width": width, "height": height}
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def extract_thumbnail(data: bytes, at_seconds: float = 0.5) -> Optional[bytes]:
    """Extract a single JPEG thumbnail from video bytes at the given time.
    Returns JPEG bytes or None if ffmpeg fails."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as inp:
        inp.write(data)
        in_path = inp.name
    out_path = in_path + ".jpg"
    try:
        cmd = [
            "ffmpeg", "-y", "-ss", str(at_seconds), "-i", in_path,
            "-vframes", "1", "-q:v", "3", "-f", "image2", out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        if result.returncode != 0 or not os.path.exists(out_path):
            logger.warning("ffmpeg thumbnail failed: %s", result.stderr.decode(errors='ignore')[:200])
            return None
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass


def probe_audio(data: bytes) -> dict:
    """ffprobe an audio file. Returns {duration_s}. Raises ValueError on failure."""
    info = probe_video(data)  # same call works
    return {"duration_s": info.get("duration_s", 0)}
