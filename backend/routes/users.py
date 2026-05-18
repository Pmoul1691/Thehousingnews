"""User-related routes: follow/unfollow, relationships, member directory, digest prefs, admin suspend."""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email, is_user_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["users"])


class DigestPrefs(BaseModel):
    am: bool = True
    pm: bool = True
    # Per-window Daily-Brief opt-ins (Phase 16). Default True so existing users
    # keep receiving briefs after the migration. Members can untick either or
    # both from the Settings page.
    brief_morning: bool = True
    brief_evening: bool = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    # ---------- Digest preferences ----------

    @router.get("/me/digest-prefs")
    async def get_digest_prefs(user=Depends(_user)):
        prefs = user.get("digest_prefs") or {}
        return {
            "am": prefs.get("am", True),
            "pm": prefs.get("pm", True),
            "brief_morning": not user.get("brief_morning_optout", False),
            "brief_evening": not user.get("brief_evening_optout", False),
        }

    @router.put("/me/digest-prefs")
    async def set_digest_prefs(payload: DigestPrefs, user=Depends(_user)):
        # Persist the legacy am/pm member-post digest knobs in digest_prefs
        # and mirror the brief on/off booleans into the top-level user doc
        # so the dispatcher's mongo filter can use them directly.
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "digest_prefs": {"am": payload.am, "pm": payload.pm},
                "brief_morning_optout": not payload.brief_morning,
                "brief_evening_optout": not payload.brief_evening,
            }},
        )
        return payload.model_dump()

    # ---------- Member directory ----------

    @router.get("/members")
    async def list_members(
        q: Optional[str] = Query(default=None),
        filter: Optional[str] = Query(default=None, regex="^(comped|supporter|free)$"),
        limit: int = Query(default=100, le=200),
        user=Depends(_user),
    ):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")

        # Only admins may filter by entitlement tier.
        if filter and not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Filter is admin-only")

        # Find approved, non-suspended users
        match = {"status": "approved", "suspended": {"$ne": True}}
        users = await db.users.find(match, {"_id": 0}).to_list(2000)
        user_ids = [u["user_id"] for u in users]
        profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(2000)
        pmap = {p["user_id"]: p for p in profiles}

        now_iso = _now_iso()
        viewer_is_admin = is_user_admin(user)

        items = []
        for u in users:
            prof = pmap.get(u["user_id"])
            if not prof:
                continue
            partner_tier = u.get("partner_tier")
            supporter_until = u.get("supporter_until")
            is_supporter = bool(supporter_until and supporter_until > now_iso)
            is_comped = bool(partner_tier) or u.get("source") == "partners_auto_grant"
            row = {
                "user_id": u["user_id"],
                "name": prof.get("name") or u.get("name") or "",
                "market": prof.get("market") or "",
                "bio": prof.get("bio") or "",
                "avatar_path": prof.get("avatar_path"),
            }
            # Only admins ever see the entitlement tier details.
            if viewer_is_admin:
                row["entitlement"] = {
                    "tier": "comped" if is_comped else ("supporter" if is_supporter else "free"),
                    "partner_tier": partner_tier,
                    "is_supporter": is_supporter,
                    "supporter_until": supporter_until,
                    "source": u.get("source"),
                    "email": u.get("email"),
                }
            # Apply admin filter (if any) after entitlement is computed.
            if filter == "comped" and not is_comped:
                continue
            if filter == "supporter" and not (is_supporter and not is_comped):
                continue
            if filter == "free" and (is_comped or is_supporter):
                continue
            items.append(row)

        if q:
            ql = q.lower().strip()
            items = [r for r in items if ql in r["name"].lower() or ql in r["market"].lower()]

        items.sort(key=lambda r: r["name"].lower())
        return {"items": items[:limit]}

    # ---------- Follows ----------

    @router.post("/users/{target_user_id}/follow")
    async def follow_user(target_user_id: str, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        if target_user_id == user["user_id"]:
            raise HTTPException(status_code=400, detail="Cannot follow yourself")
        target = await db.users.find_one({"user_id": target_user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        existing = await db.follows.find_one(
            {"follower_id": user["user_id"], "followed_id": target_user_id},
            {"_id": 0},
        )
        if not existing:
            await db.follows.insert_one({
                "follower_id": user["user_id"],
                "followed_id": target_user_id,
                "created_at": _now_iso(),
            })
        return {"is_following": True}

    @router.delete("/users/{target_user_id}/follow")
    async def unfollow_user(target_user_id: str, user=Depends(_user)):
        await db.follows.delete_one(
            {"follower_id": user["user_id"], "followed_id": target_user_id},
        )
        return {"is_following": False}

    @router.get("/users/{target_user_id}/relationship")
    async def relationship(target_user_id: str, user=Depends(_user)):
        f = await db.follows.find_one(
            {"follower_id": user["user_id"], "followed_id": target_user_id},
            {"_id": 0},
        )
        is_following = bool(f)
        # Internal-only counts (only visible on viewer's own profile)
        if target_user_id == user["user_id"]:
            following_count = await db.follows.count_documents({"follower_id": user["user_id"]})
            follower_count = await db.follows.count_documents({"followed_id": user["user_id"]})
        else:
            following_count = None
            follower_count = None
        return {
            "is_following": is_following,
            "is_self": target_user_id == user["user_id"],
            "following_count": following_count,
            "follower_count": follower_count,
        }

    @router.get("/me/following")
    async def my_following(user=Depends(_user)):
        rows = await db.follows.find({"follower_id": user["user_id"]}, {"_id": 0}).to_list(2000)
        ids = [r["followed_id"] for r in rows]
        if not ids:
            return {"items": []}
        users = await db.users.find({"user_id": {"$in": ids}, "suspended": {"$ne": True}}, {"_id": 0}).to_list(2000)
        profiles = await db.profiles.find({"user_id": {"$in": ids}}, {"_id": 0}).to_list(2000)
        pmap = {p["user_id"]: p for p in profiles}
        items = []
        for u in users:
            prof = pmap.get(u["user_id"]) or {}
            items.append({
                "user_id": u["user_id"],
                "name": prof.get("name") or u.get("name") or "",
                "market": prof.get("market") or "",
                "bio": prof.get("bio") or "",
                "avatar_path": prof.get("avatar_path"),
            })
        items.sort(key=lambda r: r["name"].lower())
        return {"items": items}

    # ---------- Admin: suspend / unsuspend ----------

    @router.post("/admin/users/{user_id}/suspend")
    async def suspend_user(user_id: str, admin=Depends(_admin)):
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        if is_user_admin(target):
            raise HTTPException(status_code=400, detail="Cannot suspend an admin")
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"suspended": True, "suspended_at": _now_iso(), "suspended_by": admin["email"]}},
        )
        return {"ok": True, "suspended": True}

    @router.post("/admin/users/{user_id}/unsuspend")
    async def unsuspend_user(user_id: str, admin=Depends(_admin)):
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"suspended": False}, "$unset": {"suspended_at": "", "suspended_by": ""}},
        )
        return {"ok": True, "suspended": False}

    return router
