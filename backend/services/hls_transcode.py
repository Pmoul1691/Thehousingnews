"""HLS transcoding: 720p single-rendition for videos longer than the inline cap.

We segment with ffmpeg to a temp dir, then upload every produced file
(master.m3u8 + seg_*.ts) to object storage under a per-job folder so the
relative URLs inside the m3u8 resolve correctly via /api/uploads/file/{path}.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone

from services.object_storage import put_object
from services.media import probe_video, extract_thumbnail

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_ffmpeg_hls(src_path: str, out_dir: str) -> None:
    """Run ffmpeg to produce master.m3u8 + segments at 720p H.264 / AAC."""
    cmd = [
        "ffmpeg", "-y", "-i", src_path,
        "-vf", "scale=w=-2:h=720:flags=lanczos",
        "-c:v", "libx264", "-profile:v", "main", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-hls_time", "4",
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", os.path.join(out_dir, "seg_%03d.ts"),
        os.path.join(out_dir, "master.m3u8"),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode(errors='ignore')[:400]}")


async def transcode_video_to_hls(db, job_id: str, user_id: str, data: bytes, content_type: str) -> dict:
    """Run the transcode in a background thread (subprocess is blocking).
    Persists every output file to object storage and updates the job row."""
    await db.transcode_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "processing", "started_at": _now_iso()}},
    )

    work_dir = tempfile.mkdtemp(prefix=f"hls_{job_id}_")
    src_path = os.path.join(work_dir, "src.bin")
    out_dir = os.path.join(work_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    try:
        with open(src_path, "wb") as f:
            f.write(data)

        # Probe duration + dimensions; extract thumbnail BEFORE ffmpeg HLS (cheap)
        meta = probe_video(data)
        duration = float(meta.get("duration_s") or 0)
        if duration <= 0:
            raise RuntimeError("Could not read video duration")

        thumb_bytes = extract_thumbnail(data, at_seconds=min(1.0, duration / 4))
        thumbnail_path = None
        if thumb_bytes:
            tpath = f"posts/{user_id}/hls/{job_id}/thumbnail.jpg"
            put_object(tpath, thumb_bytes, "image/jpeg")
            await db.files.insert_one({
                "user_id": user_id, "storage_path": tpath, "original_filename": "thumbnail.jpg",
                "content_type": "image/jpeg", "size": len(thumb_bytes), "kind": "posts",
                "media_kind": "image", "is_deleted": False, "created_at": _now_iso(),
            })
            thumbnail_path = tpath

        # Run ffmpeg in a thread so we don't block the event loop
        await asyncio.to_thread(_run_ffmpeg_hls, src_path, out_dir)

        # Upload every produced file
        base_path = f"posts/{user_id}/hls/{job_id}"
        produced = sorted(os.listdir(out_dir))
        for name in produced:
            full = os.path.join(out_dir, name)
            with open(full, "rb") as f:
                blob = f.read()
            ct = "application/vnd.apple.mpegurl" if name.endswith(".m3u8") else "video/mp2t"
            storage_path = f"{base_path}/{name}"
            put_object(storage_path, blob, ct)
            await db.files.insert_one({
                "user_id": user_id, "storage_path": storage_path, "original_filename": name,
                "content_type": ct, "size": len(blob), "kind": "posts",
                "media_kind": "hls_segment" if name.endswith(".ts") else "hls_manifest",
                "is_deleted": False, "created_at": _now_iso(),
            })

        hls_path = f"{base_path}/master.m3u8"
        await db.transcode_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "ready",
                "hls_path": hls_path,
                "thumbnail_path": thumbnail_path,
                "duration_s": round(duration, 2),
                "width": meta.get("width") or 0,
                "height": meta.get("height") or 0,
                "completed_at": _now_iso(),
            }},
        )
        return {"status": "ready", "hls_path": hls_path}
    except Exception as e:
        logger.exception("HLS transcode failed for %s", job_id)
        await db.transcode_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(e)[:300], "completed_at": _now_iso()}},
        )
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
