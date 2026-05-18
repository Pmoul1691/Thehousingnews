"""Admin: list recent posts + take down / restore.

The hide/unhide endpoints live in routes/moderation.py and we keep using
those. This router adds the listing + search that the admin UI needs to
browse posts without going through the flag queue.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header, Query

from services.auth_helpers import get_current_user, is_user_admin

logger = logging.getLogger(__name__)


def setup(db):
    router = APIRouter(prefix="/api/admin/posts", tags=["admin-posts"])

    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/recent")
    async def list_recent_posts(
        status: Optional[str] = Query(default=None),
        q: Optional[str] = Query(default=None, max_length=200),
        kind: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        match = {}
        if status:
            match["status"] = status
        if kind:
            match["kind"] = kind
        if q:
            import re as _re
            pat = _re.escape(q.strip())
            match["$or"] = [
                {"title": {"$regex": pat, "$options": "i"}},
                {"text": {"$regex": pat, "$options": "i"}},
            ]
        posts = await db.posts.find(
            match,
            {
                "_id": 0, "post_id": 1, "title": 1, "subtitle": 1, "text": 1,
                "user_id": 1, "kind": 1, "status": 1, "release_at": 1,
                "created_at": 1, "hidden_at": 1, "hidden_by": 1,
                "image_path": 1, "source": 1,
            },
        ).sort("created_at", -1).limit(limit).to_list(limit)
        user_ids = list({p.get("user_id") for p in posts if p.get("user_id")})
        users_by_id = {}
        if user_ids:
            async for u in db.users.find(
                {"user_id": {"$in": user_ids}},
                {"_id": 0, "user_id": 1, "name": 1, "email": 1},
            ):
                users_by_id[u["user_id"]] = u
        profiles_by_id = {}
        if user_ids:
            async for p in db.profiles.find(
                {"user_id": {"$in": user_ids}},
                {"_id": 0, "user_id": 1, "name": 1, "avatar_path": 1},
            ):
                profiles_by_id[p["user_id"]] = p

        items = []
        for p in posts:
            uid = p.get("user_id")
            u = users_by_id.get(uid) or {}
            prof = profiles_by_id.get(uid) or {}
            snippet = (p.get("text") or "").strip()
            if len(snippet) > 280:
                snippet = snippet[:280].rstrip() + "…"
            items.append({
                "post_id": p["post_id"],
                "title": p.get("title") or "",
                "subtitle": p.get("subtitle") or "",
                "snippet": snippet,
                "kind": p.get("kind") or "short",
                "status": p.get("status") or "",
                "release_at": p.get("release_at"),
                "created_at": p.get("created_at"),
                "hidden_at": p.get("hidden_at"),
                "hidden_by": p.get("hidden_by"),
                "image_path": p.get("image_path"),
                "source": p.get("source"),
                "author": {
                    "user_id": uid,
                    "name": prof.get("name") or u.get("name") or "",
                    "email": u.get("email") or "",
                    "avatar_path": prof.get("avatar_path"),
                },
            })
        return {"items": items, "count": len(items)}

    return router
