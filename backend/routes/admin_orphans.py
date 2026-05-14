"""Admin: surface and reconnect orphan profiles.

An "orphan" profile is a profile document whose `user_id` no longer matches any
user in `users` (typically due to a manual deletion or migration). When the
original member signs in again with their Google email, the new user gets a
fresh user_id, leaving the old profile stranded with their bio + market history.

This module lets admins (1) list orphans and (2) re-stitch a profile to the
current user with the same email in one click. Reconnect updates:
- profiles.user_id -> users.user_id (matched by email)
- posts.user_id    -> users.user_id (so essays/posts re-attribute under the live user)
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel

from services.auth_helpers import get_current_user, is_admin_email

logger = logging.getLogger(__name__)


class ReconnectPayload(BaseModel):
    profile_email: str


def setup(db):
    router = APIRouter(prefix="/api/admin/orphan-profiles", tags=["admin-orphans"])

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("")
    async def list_orphans(_admin=Depends(_admin)):
        """Return profiles whose user_id no longer exists in users.
        For each orphan, attach the candidate live user (matched by email) if one exists."""
        profiles = await db.profiles.find({}, {"_id": 0}).to_list(2000)
        if not profiles:
            return {"items": []}
        user_ids = list({p["user_id"] for p in profiles if p.get("user_id")})
        live_users = await db.users.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1},
        ).to_list(2000)
        live_set = {u["user_id"] for u in live_users}
        orphans = [p for p in profiles if p.get("user_id") not in live_set]
        if not orphans:
            return {"items": []}
        emails = list({p.get("email", "").lower() for p in orphans if p.get("email")})
        candidates = await db.users.find(
            {"email": {"$in": emails}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "status": 1},
        ).to_list(2000)
        cand_map = {u["email"].lower(): u for u in candidates if u.get("email")}
        items = []
        for p in orphans:
            email = (p.get("email") or "").lower()
            cand = cand_map.get(email)
            # Quick stats: how many posts under the orphan user_id
            post_count = await db.posts.count_documents({"user_id": p["user_id"]})
            items.append({
                "profile_user_id": p["user_id"],
                "email": p.get("email"),
                "name": p.get("name"),
                "market": p.get("market"),
                "post_count": post_count,
                "candidate_user": cand,  # None if no live user matches
            })
        return {"items": items}

    @router.post("/reconnect")
    async def reconnect(payload: ReconnectPayload, admin=Depends(_admin)):
        """Re-stitch an orphan profile to its live user (by email).

        Updates profile.user_id and reassigns any posts authored under the orphan
        user_id over to the live user_id. Idempotent.
        """
        email = (payload.profile_email or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="profile_email required")

        live = await db.users.find_one({"email": email}, {"_id": 0})
        if not live:
            raise HTTPException(status_code=404, detail="No live user found for that email")

        # Find the orphan profile by email (excluding the live user's own profile,
        # if one already exists with the matching user_id).
        orphan = await db.profiles.find_one(
            {"email": {"$regex": f"^{email}$", "$options": "i"}, "user_id": {"$ne": live["user_id"]}},
            {"_id": 0},
        )
        if not orphan:
            raise HTTPException(status_code=404, detail="No orphan profile with that email")

        old_user_id = orphan["user_id"]
        new_user_id = live["user_id"]
        now_iso = datetime.now(timezone.utc).isoformat()

        # If a profile already exists under the new user_id, keep the orphan's content
        # (bio/objectives) but drop the placeholder under the new id first.
        existing_under_new = await db.profiles.find_one({"user_id": new_user_id}, {"_id": 0})
        if existing_under_new:
            await db.profiles.delete_one({"user_id": new_user_id})

        await db.profiles.update_one(
            {"user_id": old_user_id},
            {"$set": {"user_id": new_user_id, "updated_at": now_iso}},
        )

        posts_result = await db.posts.update_many(
            {"user_id": old_user_id},
            {"$set": {"user_id": new_user_id}},
        )
        replies_result = await db.replies.update_many(
            {"user_id": old_user_id},
            {"$set": {"user_id": new_user_id}},
        )

        logger.info(
            "orphan profile reconnected admin=%s email=%s old=%s new=%s posts=%d replies=%d",
            admin["email"], email, old_user_id, new_user_id,
            posts_result.modified_count, replies_result.modified_count,
        )

        return {
            "reconnected": True,
            "email": email,
            "old_user_id": old_user_id,
            "new_user_id": new_user_id,
            "posts_reassigned": posts_result.modified_count,
            "replies_reassigned": replies_result.modified_count,
        }

    return router
