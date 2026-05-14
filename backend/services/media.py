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


def extract_audio_peaks(data: bytes, buckets: int = 200) -> list[float]:
    """Decode an audio file to mono PCM via ffmpeg and reduce to `buckets`
    normalized peak values (0.0 - 1.0). Returns an empty list on failure.

    The peaks are intended to drive a static SVG waveform on the client:
    cheap to ship, no Web Audio API decode work needed at view time.
    """
    if not data:
        return []
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as inp:
        inp.write(data)
        in_path = inp.name
    try:
        cmd = [
            "ffmpeg", "-v", "error", "-i", in_path,
            "-ac", "1",                     # mono
            "-filter:a", "aresample=8000",  # cheap downsample, plenty for peaks
            "-map", "0:a",
            "-c:a", "pcm_s16le",
            "-f", "s16le", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            logger.warning("ffmpeg peaks failed: %s", result.stderr.decode(errors="ignore")[:200])
            return []
        pcm = result.stdout
        if not pcm:
            return []
        # int16 little-endian -> abs amplitudes
        import struct
        sample_count = len(pcm) // 2
        if sample_count == 0:
            return []
        bucket_size = max(1, sample_count // buckets)
        peaks: list[float] = []
        for i in range(buckets):
            start = i * bucket_size * 2
            end = start + bucket_size * 2
            chunk = pcm[start:end]
            if not chunk:
                break
            samples = struct.unpack(f"<{len(chunk)//2}h", chunk)
            peak = max(abs(s) for s in samples) if samples else 0
            peaks.append(peak)
        if not peaks:
            return []
        m = max(peaks) or 1
        return [round(p / m, 3) for p in peaks]
    except Exception as e:
        logger.warning("extract_audio_peaks failed: %s", e)
        return []
    finally:
        try:
            os.unlink(in_path)
        except Exception:
            pass
