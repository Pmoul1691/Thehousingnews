"""Post composer and feeds."""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["posts"])


class PostCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    image_path: Optional[str] = None


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    async def _attach_authors(items: List[dict]) -> List[dict]:
        user_ids = list({p["user_id"] for p in items})
        if not user_ids:
            return items
        profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        profile_map = {p["user_id"]: p for p in profiles}
        user_map = {u["user_id"]: u for u in users}
        for p in items:
            prof = profile_map.get(p["user_id"])
            usr = user_map.get(p["user_id"], {})
            p["author"] = {
                "user_id": p["user_id"],
                "name": (prof or {}).get("name") or usr.get("name") or "Member",
                "market": (prof or {}).get("market"),
                "avatar_path": (prof or {}).get("avatar_path"),
            }
        return items

    @router.post("")
    async def create_post(payload: PostCreate, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        post_id = f"post_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        doc = {
            "post_id": post_id,
            "user_id": user["user_id"],
            "text": payload.text.strip(),
            "image_path": payload.image_path,
            "status": "approved",  # Phase 1: instant publish
            "created_at": now_iso,
            "release_at": now_iso,
        }
        await db.posts.insert_one(doc)
        return {"post_id": post_id, "created_at": now_iso}

    @router.get("/public")
    async def public_feed(limit: int = Query(50, le=100)):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        cur = db.posts.find(
            {"status": "approved", "created_at": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit)
        items = await cur.to_list(limit)
        items = await _attach_authors(items)
        return {"items": items}

    @router.get("/feed")
    async def home_feed(limit: int = Query(50, le=100), user=Depends(_user)):
        if user.get("status") != "approved":
            return {"items": []}
        # Phase 1 has no follows yet, so home feed = author's own posts + everyone in last 14 days
        # but limited and ordered. For the "personal" feed we show own posts first, then network.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        cur = db.posts.find(
            {"status": "approved", "created_at": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit)
        items = await cur.to_list(limit)
        items = await _attach_authors(items)
        return {"items": items}

    @router.get("/by-user/{user_id}")
    async def posts_by_user(user_id: str, user=Depends(_user)):
        cur = db.posts.find({"user_id": user_id, "status": "approved"}, {"_id": 0}).sort("created_at", -1).limit(50)
        items = await cur.to_list(50)
        items = await _attach_authors(items)
        return {"items": items}

    return router
