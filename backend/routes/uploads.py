"""File upload routes (avatars + post images)."""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, UploadFile, File, Form, Response

from services.auth_helpers import get_current_user
from services.object_storage import put_object, get_object, build_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_SIZE = 6 * 1024 * 1024  # 6MB


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.post("")
    async def upload(
        file: UploadFile = File(...),
        kind: str = Form("posts"),
        user=Depends(_user),
    ):
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported image type")
        if kind not in ("avatars", "posts"):
            kind = "posts"
        data = await file.read()
        if len(data) > MAX_SIZE:
            raise HTTPException(status_code=413, detail="Image too large (max 6MB)")
        ext = ALLOWED_TYPES[content_type]
        path = build_path(user["user_id"], kind, ext)
        try:
            result = put_object(path, data, content_type)
        except Exception as e:
            logger.exception("Object storage upload failed")
            raise HTTPException(status_code=502, detail=f"Upload failed: {e}")
        record = {
            "user_id": user["user_id"],
            "storage_path": result["path"],
            "original_filename": file.filename,
            "content_type": content_type,
            "size": result.get("size", len(data)),
            "kind": kind,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.files.insert_one(record)
        return {"path": result["path"], "size": record["size"], "content_type": content_type}

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
