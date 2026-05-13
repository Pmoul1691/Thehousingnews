"""Admin manual trigger for the Substack RSS import."""
import logging
from typing import Optional
from fastapi import APIRouter, Cookie, Header, HTTPException

from services.auth_helpers import get_current_user, is_admin_email
from services.substack_import import import_substack_feed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/rss", tags=["admin-rss"])


def setup(db):
    async def _require_admin(session_token: Optional[str], authorization: Optional[str]):
        user = await get_current_user(db, session_token, authorization)
        if not (user.get("is_admin") or is_admin_email(user["email"])):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.post("/import")
    async def manual_import(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _require_admin(session_token, authorization)
        result = await import_substack_feed(db)
        return result

    @router.get("/status")
    async def status(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _require_admin(session_token, authorization)
        total = await db.posts.count_documents({"source": "substack_import"})
        recent = await db.posts.find(
            {"source": "substack_import"},
            {"_id": 0, "post_id": 1, "title": 1, "release_at": 1, "imported_at": 1, "source_url": 1},
        ).sort("imported_at", -1).limit(20).to_list(20)
        return {"imported_total": total, "recent": recent}

    return router
