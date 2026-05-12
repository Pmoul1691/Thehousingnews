"""Replies on posts. Same batched release model as posts."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user
from services.release_window import next_window, CHICAGO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["replies"])


class ReplyCreate(BaseModel):
    text: str = Field(min_length=1, max_length=300)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.post("/{post_id}/replies")
    async def create_reply(post_id: str, payload: ReplyCreate, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        post = await db.posts.find_one({"post_id": post_id}, {"_id": 0})
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        reply_id = f"reply_{uuid.uuid4().hex[:12]}"
        release_at = next_window(datetime.now(CHICAGO)).astimezone(timezone.utc).isoformat()
        doc = {
            "reply_id": reply_id,
            "post_id": post_id,
            "user_id": user["user_id"],
            "text": payload.text.strip(),
            "status": "pending_release",
            "created_at": _now_iso(),
            "release_at": release_at,
        }
        await db.replies.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.get("/{post_id}/replies")
    async def list_replies(
        post_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        # Optional auth. If signed-in approved member, also return their own pending replies.
        viewer = None
        try:
            viewer = await get_current_user(db, session_token, authorization)
        except Exception:
            viewer = None

        now_iso = _now_iso()
        # Released replies (status=approved OR release_at<=now)
        released = await db.replies.find(
            {"post_id": post_id, "release_at": {"$lte": now_iso}},
            {"_id": 0},
        ).sort("created_at", 1).to_list(200)

        items = released
        if viewer and viewer.get("status") == "approved":
            own_pending = await db.replies.find(
                {"post_id": post_id, "user_id": viewer["user_id"], "release_at": {"$gt": now_iso}},
                {"_id": 0},
            ).sort("created_at", 1).to_list(50)
            items = items + own_pending

        # Attach authors
        if items:
            user_ids = list({r["user_id"] for r in items})
            profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
            users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
            pmap = {p["user_id"]: p for p in profiles}
            umap = {u["user_id"]: u for u in users}
            for r in items:
                prof = pmap.get(r["user_id"])
                usr = umap.get(r["user_id"], {})
                r["author"] = {
                    "user_id": r["user_id"],
                    "name": (prof or {}).get("name") or usr.get("name") or "Member",
                    "avatar_path": (prof or {}).get("avatar_path"),
                    "market": (prof or {}).get("market"),
                }
                r["is_released"] = r.get("release_at", "") <= now_iso
        return {"items": items}

    return router
