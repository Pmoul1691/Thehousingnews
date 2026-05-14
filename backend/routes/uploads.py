"""File upload routes (images, video, audio). Auto-generates a thumbnail for video uploads."""
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, UploadFile, File, Form, Response, BackgroundTasks
from PIL import Image, ImageOps

from services.auth_helpers import get_current_user
from services.object_storage import put_object, get_object, build_path
from services.media import probe_video, extract_thumbnail, extract_audio_peaks
from services.embed import parse_embed
from services.hls_transcode import transcode_video_to_hls

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
}
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}

MAX_IMAGE_SIZE = 6 * 1024 * 1024     # 6 MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024    # 50 MB direct MP4
MAX_VIDEO_HLS_SIZE = 200 * 1024 * 1024  # 200 MB longer videos that get HLS-transcoded
MAX_AUDIO_SIZE = 20 * 1024 * 1024    # 20 MB
INLINE_VIDEO_SECONDS = 60            # videos this short stay as direct MP4
MAX_VIDEO_SECONDS = 180              # 3 minutes total cap
MAX_AUDIO_SECONDS = 5 * 60

# Resize images > this threshold to keep payloads reasonable
RESIZE_TRIGGER_BYTES = 1 * 1024 * 1024  # 1 MB
RESIZE_MAX_DIM = 1920
RESIZE_JPEG_QUALITY = 85


def _maybe_resize_image(data: bytes, content_type: str) -> tuple[bytes, str]:
    """If the image is larger than RESIZE_TRIGGER_BYTES, downscale + recompress.
    GIFs are left alone (animation would be destroyed by Pillow's default save).
    Returns (new_bytes, new_content_type)."""
    if len(data) <= RESIZE_TRIGGER_BYTES:
        return data, content_type
    if content_type == "image/gif":
        return data, content_type
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        # Force RGB(A); JPEG cannot save RGBA.
        target_ct = "image/jpeg"
        if content_type == "image/png" and img.mode in ("RGBA", "LA"):
            target_ct = "image/png"
        if target_ct == "image/jpeg" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        img.thumbnail((RESIZE_MAX_DIM, RESIZE_MAX_DIM), Image.LANCZOS)
        out = io.BytesIO()
        if target_ct == "image/jpeg":
            img.save(out, format="JPEG", quality=RESIZE_JPEG_QUALITY, optimize=True, progressive=True)
        else:
            img.save(out, format="PNG", optimize=True)
        return out.getvalue(), target_ct
    except Exception:
        logger.exception("image resize failed; storing original")
        return data, content_type


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    async def _persist(user_id: str, kind: str, content_type: str, data: bytes, extra: dict, filename: str) -> dict:
        ext = (ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES | ALLOWED_AUDIO_TYPES).get(content_type, "bin")
        path = build_path(user_id, kind, ext)
        try:
            result = put_object(path, data, content_type)
        except Exception as e:
            logger.exception("Object storage upload failed")
            raise HTTPException(status_code=502, detail=f"Upload failed: {e}")
        record = {
            "user_id": user_id,
            "storage_path": result["path"],
            "original_filename": filename,
            "content_type": content_type,
            "size": result.get("size", len(data)),
            "kind": kind,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        await db.files.insert_one(record)
        return {"path": result["path"], "size": record["size"], "content_type": content_type, **extra}

    @router.post("")
    async def upload(
        background: BackgroundTasks,
        file: UploadFile = File(...),
        kind: str = Form("posts"),
        user=Depends(_user),
    ):
        if user.get("status") != "approved" and kind != "avatars":
            raise HTTPException(status_code=403, detail="Membership not approved")
        content_type = (file.content_type or "").lower()
        data = await file.read()

        # avatars: image only, 6MB cap
        if kind == "avatars":
            if content_type not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(status_code=400, detail="Avatars must be an image")
            if len(data) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=413, detail="Image too large (max 6MB)")
            data, content_type = _maybe_resize_image(data, content_type)
            return await _persist(user["user_id"], "avatars", content_type, data, {}, file.filename or "")

        # image
        if content_type in ALLOWED_IMAGE_TYPES:
            if len(data) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=413, detail="Image too large (max 6MB)")
            data, content_type = _maybe_resize_image(data, content_type)
            return await _persist(user["user_id"], "posts", content_type, data, {"media_kind": "image"}, file.filename or "")

        # video
        if content_type in ALLOWED_VIDEO_TYPES:
            if len(data) > MAX_VIDEO_HLS_SIZE:
                raise HTTPException(status_code=413, detail=f"Video too large (max {MAX_VIDEO_HLS_SIZE // (1024*1024)}MB)")
            try:
                meta = probe_video(data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Could not read video: {e}")
            duration = float(meta.get("duration_s") or 0)
            if duration <= 0:
                raise HTTPException(status_code=400, detail="Video has no readable duration")
            if duration > MAX_VIDEO_SECONDS + 0.5:
                raise HTTPException(status_code=400, detail=f"Video must be {MAX_VIDEO_SECONDS} seconds or shorter")

            # Long videos: queue an async HLS transcode and return immediately.
            if duration > INLINE_VIDEO_SECONDS:
                job_id = uuid.uuid4().hex
                await db.transcode_jobs.insert_one({
                    "job_id": job_id,
                    "user_id": user["user_id"],
                    "status": "queued",
                    "duration_s": round(duration, 2),
                    "width": meta.get("width") or 0,
                    "height": meta.get("height") or 0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "hls_path": None,
                    "thumbnail_path": None,
                    "error": None,
                })
                background.add_task(transcode_video_to_hls, db, job_id, user["user_id"], data, content_type)
                return {
                    "media_kind": "video",
                    "processing": True,
                    "transcode_job_id": job_id,
                    "duration_s": round(duration, 2),
                    "width": meta.get("width") or 0,
                    "height": meta.get("height") or 0,
                }

            # Short videos: inline MP4 path with poster thumbnail (existing behavior).
            if len(data) > MAX_VIDEO_SIZE:
                raise HTTPException(status_code=413, detail=f"Inline video too large (max {MAX_VIDEO_SIZE // (1024*1024)}MB; longer videos auto-transcode)")
            extra = {
                "media_kind": "video",
                "duration_s": round(duration, 2),
                "width": meta.get("width") or 0,
                "height": meta.get("height") or 0,
            }
            thumb_bytes = extract_thumbnail(data, at_seconds=min(0.5, max(0.0, duration / 4)))
            if thumb_bytes:
                thumb_record = await _persist(
                    user["user_id"], "posts", "image/jpeg", thumb_bytes,
                    {"media_kind": "image", "is_thumbnail_of": True}, "thumbnail.jpg",
                )
                extra["thumbnail_path"] = thumb_record["path"]
            return await _persist(user["user_id"], "posts", content_type, data, extra, file.filename or "")

        # audio
        if content_type in ALLOWED_AUDIO_TYPES:
            if len(data) > MAX_AUDIO_SIZE:
                raise HTTPException(status_code=413, detail="Audio too large (max 20MB)")
            try:
                meta = probe_video(data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Could not read audio: {e}")
            duration = float(meta.get("duration_s") or 0)
            if duration > MAX_AUDIO_SECONDS + 0.5:
                raise HTTPException(status_code=400, detail=f"Audio must be {MAX_AUDIO_SECONDS // 60} minutes or shorter")
            extra = {"media_kind": "audio", "duration_s": round(duration, 2)}
            # Compute a static 200-bucket waveform preview - cheap to ship and
            # avoids client-side Web Audio decoding for every viewer.
            try:
                peaks = extract_audio_peaks(data, buckets=200)
                if peaks:
                    extra["peaks"] = peaks
            except Exception as _e:
                logger.warning("audio peaks failed: %s", _e)
            return await _persist(user["user_id"], "posts", content_type, data, extra, file.filename or "")

        raise HTTPException(status_code=400, detail="Unsupported file type")

    @router.post("/embed")
    async def parse_url(payload: dict, user=Depends(_user)):
        url = (payload or {}).get("url", "")
        result = parse_embed(url)
        if not result:
            raise HTTPException(status_code=400, detail="Only YouTube or Vimeo URLs are supported")
        return result

    @router.get("/transcode/{job_id}")
    async def transcode_status(job_id: str, user=Depends(_user)):
        row = await db.transcode_jobs.find_one({"job_id": job_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        if row.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Not your job")
        return row

    # Serve files. Public-ish: anyone can fetch by path (since profile photos are public).
    @router.get("/file/{path:path}")
    async def get_file(path: str):
        rec = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="File not found")
        try:
            data, ct = get_object(path)
        except Exception:
            logger.exception("Object fetch failed")
            raise HTTPException(status_code=404, detail="File not found")
        return Response(content=data, media_type=rec.get("content_type") or ct)

    return router
