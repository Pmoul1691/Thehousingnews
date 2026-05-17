"""Pete's pick of the week - admin curation."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header

from services.auth_helpers import get_current_user, is_admin_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["picks"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.post("/admin/posts/{post_id}/pick")
    async def pick(post_id: str, admin=Depends(_admin)):
        post = await db.posts.find_one({"post_id": post_id}, {"_id": 0})
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        await db.posts.update_one(
            {"post_id": post_id},
            {"$set": {"is_pete_pick": True, "pete_picked_at": _now_iso(), "pete_picked_by": admin["email"]}},
        )
        return {"ok": True, "is_pete_pick": True}

    @router.post("/admin/posts/{post_id}/unpick")
    async def unpick(post_id: str, admin=Depends(_admin)):
        r = await db.posts.update_one(
            {"post_id": post_id},
            {"$set": {"is_pete_pick": False}, "$unset": {"pete_picked_at": "", "pete_picked_by": ""}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Post not found")
        return {"ok": True, "is_pete_pick": False}

    @router.get("/posts/picks")
    async def list_picks(limit: int = 5):
        """Public. Most recent Pete picks from the last 30 days."""
        now_iso = _now_iso()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        # Find Pete picks that are released and not hidden
        cur = db.posts.find(
            {
                "is_pete_pick": True,
                "release_at": {"$lte": now_iso, "$gte": cutoff},
                "status": {"$nin": ["declined", "hidden", "flagged_by_ai"]},
            },
            {"_id": 0},
        ).sort("pete_picked_at", -1).limit(limit)
        items = await cur.to_list(limit)

        # Filter out suspended authors
        if items:
            user_ids = list({p["user_id"] for p in items})
            suspended = await db.users.find(
                {"user_id": {"$in": user_ids}, "suspended": True},
                {"_id": 0, "user_id": 1},
            ).to_list(500)
            sus_ids = {s["user_id"] for s in suspended}
            items = [p for p in items if p["user_id"] not in sus_ids]
            profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
            users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
            pmap = {p["user_id"]: p for p in profiles}
            umap = {u["user_id"]: u for u in users}
            now = _now_iso()
            for p in items:
                prof = pmap.get(p["user_id"]) or {}
                usr = umap.get(p["user_id"]) or {}
                p["author"] = {
                    "user_id": p["user_id"],
                    "name": prof.get("name") or usr.get("name") or "Member",
                    "market": prof.get("market"),
                    "avatar_path": prof.get("avatar_path"),
                    "is_supporter": (usr.get("supporter_until") or "") > now,
                }
                p["is_released"] = True
                p["reply_count"] = 0
        return {"items": items}

    return router
