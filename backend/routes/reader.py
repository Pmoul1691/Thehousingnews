"""Reader-side routes: bookmarks (save for later) and reads (mark-as-read)."""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me", tags=["reader"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.post("/bookmarks/{post_id}")
    async def add_bookmark(post_id: str, user=Depends(_user)):
        post = await db.posts.find_one({"post_id": post_id}, {"_id": 0, "post_id": 1, "kind": 1})
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        try:
            await db.bookmarks.insert_one({
                "user_id": user["user_id"],
                "post_id": post_id,
                "created_at": _now_iso(),
            })
        except Exception:
            pass  # duplicate is fine
        return {"is_bookmarked": True}

    @router.delete("/bookmarks/{post_id}")
    async def remove_bookmark(post_id: str, user=Depends(_user)):
        await db.bookmarks.delete_one({"user_id": user["user_id"], "post_id": post_id})
        return {"is_bookmarked": False}

    @router.get("/bookmarks")
    async def list_bookmarks(user=Depends(_user)):
        rows = await db.bookmarks.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        if not rows:
            return {"items": []}
        post_ids = [r["post_id"] for r in rows]
        now_iso = _now_iso()
        posts = await db.posts.find(
            {"post_id": {"$in": post_ids}, "kind": "essay", "release_at": {"$lte": now_iso}, "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0},
        ).to_list(500)
        post_map = {p["post_id"]: p for p in posts}

        user_ids = list({p["user_id"] for p in posts})
        profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        pmap = {p["user_id"]: p for p in profiles}

        items = []
        for r in rows:
            p = post_map.get(r["post_id"])
            if not p:
                continue
            prof = pmap.get(p["user_id"]) or {}
            items.append({
                "post_id": p["post_id"],
                "title": p.get("title"),
                "subtitle": p.get("subtitle"),
                "image_path": p.get("image_path"),
                "release_at": p.get("release_at"),
                "bookmarked_at": r.get("created_at"),
                "author": {
                    "user_id": p["user_id"],
                    "name": prof.get("name") or "Member",
                    "market": prof.get("market"),
                    "avatar_path": prof.get("avatar_path"),
                },
            })
        return {"items": items}

    @router.get("/bookmarks/{post_id}")
    async def is_bookmarked(post_id: str, user=Depends(_user)):
        b = await db.bookmarks.find_one({"user_id": user["user_id"], "post_id": post_id}, {"_id": 0})
        return {"is_bookmarked": bool(b)}

    @router.post("/reads/{post_id}")
    async def mark_read(post_id: str, user=Depends(_user)):
        try:
            await db.reads.update_one(
                {"user_id": user["user_id"], "post_id": post_id},
                {"$set": {"read_at": _now_iso()}, "$setOnInsert": {"created_at": _now_iso()}},
                upsert=True,
            )
        except Exception:
            pass
        return {"is_read": True}

    @router.get("/reads")
    async def list_reads(user=Depends(_user)):
        rows = await db.reads.find({"user_id": user["user_id"]}, {"_id": 0, "post_id": 1, "read_at": 1}).to_list(2000)
        return {"items": rows}

    return router
