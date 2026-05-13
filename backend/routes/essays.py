"""Essay-specific routes: single essay reader with paywall for non-members."""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/essays", tags=["essays"])

PREVIEW_CHARS = 320


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "..."


def setup(db):
    @router.get("/{post_id}")
    async def get_essay(
        post_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        post = await db.posts.find_one(
            {"post_id": post_id, "kind": "essay", "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0},
        )
        if not post:
            raise HTTPException(status_code=404, detail="Essay not found")

        owner = await db.users.find_one({"user_id": post["user_id"]}, {"_id": 0})
        if owner and owner.get("suspended"):
            raise HTTPException(status_code=404, detail="Essay not found")

        # Author
        profile = await db.profiles.find_one({"user_id": post["user_id"]}, {"_id": 0})
        now_iso = _now_iso()
        author = {
            "user_id": post["user_id"],
            "name": (profile or {}).get("name") or (owner or {}).get("name") or "Member",
            "market": (profile or {}).get("market"),
            "avatar_path": (profile or {}).get("avatar_path"),
            "bio": (profile or {}).get("bio"),
            "is_supporter": ((owner or {}).get("supporter_until") or "") > now_iso,
        }

        # Reply count (released only)
        reply_count = await db.replies.count_documents({
            "post_id": post_id,
            "release_at": {"$lte": now_iso},
            "status": {"$ne": "hidden"},
        })

        # Determine viewer
        viewer = None
        try:
            viewer = await get_current_user(db, session_token, authorization)
        except Exception:
            viewer = None

        is_member = viewer is not None and viewer.get("status") == "approved"

        body = {
            "post_id": post["post_id"],
            "kind": "essay",
            "title": post.get("title"),
            "subtitle": post.get("subtitle"),
            "image_path": post.get("image_path"),
            "created_at": post.get("created_at"),
            "release_at": post.get("release_at"),
            "is_pete_pick": bool(post.get("is_pete_pick")),
            "is_released": True,
            "author": author,
            "reply_count": reply_count,
            "is_member_only": True,
        }

        if is_member:
            body["text"] = post.get("text") or ""
            body["paywall"] = False
        else:
            body["preview"] = _preview(post.get("text") or "")
            body["paywall"] = True

        return body

    return router
