"""Moderation routes: members can flag posts/replies; admins resolve via hide/unhide."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["moderation"])


class FlagCreate(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300)


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
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    # ---------- Member: flag ----------

    async def _create_flag(target_kind: str, target_id: str, target_owner_id: str, user: dict, reason: Optional[str]):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        # Idempotent per user+target
        existing = await db.flags.find_one(
            {"target_kind": target_kind, "target_id": target_id, "flagger_id": user["user_id"], "resolved": False},
            {"_id": 0},
        )
        if existing:
            return existing
        flag = {
            "flag_id": f"flag_{uuid.uuid4().hex[:12]}",
            "target_kind": target_kind,
            "target_id": target_id,
            "target_owner_id": target_owner_id,
            "flagger_id": user["user_id"],
            "flagger_email": user["email"],
            "reason": (reason or "").strip(),
            "resolved": False,
            "created_at": _now_iso(),
            "resolved_at": None,
            "resolved_by": None,
            "resolution": None,
        }
        await db.flags.insert_one(flag)
        flag.pop("_id", None)
        return flag

    @router.post("/posts/{post_id}/flag")
    async def flag_post(post_id: str, payload: FlagCreate, user=Depends(_user)):
        post = await db.posts.find_one({"post_id": post_id}, {"_id": 0})
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return await _create_flag("post", post_id, post["user_id"], user, payload.reason)

    @router.post("/replies/{reply_id}/flag")
    async def flag_reply(reply_id: str, payload: FlagCreate, user=Depends(_user)):
        reply = await db.replies.find_one({"reply_id": reply_id}, {"_id": 0})
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")
        return await _create_flag("reply", reply_id, reply["user_id"], user, payload.reason)

    # ---------- Admin: queue + actions ----------

    @router.get("/admin/flags")
    async def list_flags(
        status: Literal["open", "resolved"] = "open",
        admin=Depends(_admin),
    ):
        match = {"resolved": status == "resolved"}
        flags = await db.flags.find(match, {"_id": 0}).sort("created_at", -1).to_list(500)

        # Hydrate target snippets
        post_ids = [f["target_id"] for f in flags if f["target_kind"] == "post"]
        reply_ids = [f["target_id"] for f in flags if f["target_kind"] == "reply"]
        owner_ids = list({f["target_owner_id"] for f in flags})

        posts = await db.posts.find({"post_id": {"$in": post_ids}}, {"_id": 0}).to_list(500) if post_ids else []
        replies = await db.replies.find({"reply_id": {"$in": reply_ids}}, {"_id": 0}).to_list(500) if reply_ids else []
        owners = await db.users.find({"user_id": {"$in": owner_ids}}, {"_id": 0}).to_list(500)
        profiles = await db.profiles.find({"user_id": {"$in": owner_ids}}, {"_id": 0}).to_list(500)

        post_map = {p["post_id"]: p for p in posts}
        reply_map = {r["reply_id"]: r for r in replies}
        owner_map = {u["user_id"]: u for u in owners}
        profile_map = {p["user_id"]: p for p in profiles}

        items = []
        for f in flags:
            tgt = post_map.get(f["target_id"]) if f["target_kind"] == "post" else reply_map.get(f["target_id"])
            owner = owner_map.get(f["target_owner_id"], {})
            prof = profile_map.get(f["target_owner_id"], {})
            items.append({
                **f,
                "target": tgt,
                "owner": {
                    "user_id": f["target_owner_id"],
                    "name": (prof or {}).get("name") or owner.get("name") or "Member",
                    "email": owner.get("email"),
                    "suspended": owner.get("suspended", False),
                },
            })
        return {"items": items}

    @router.post("/admin/posts/{post_id}/hide")
    async def hide_post(post_id: str, admin=Depends(_admin)):
        r = await db.posts.update_one({"post_id": post_id}, {"$set": {"status": "hidden", "hidden_at": _now_iso(), "hidden_by": admin["email"]}})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Post not found")
        # Auto-resolve open flags on this post
        await db.flags.update_many(
            {"target_kind": "post", "target_id": post_id, "resolved": False},
            {"$set": {"resolved": True, "resolved_at": _now_iso(), "resolved_by": admin["email"], "resolution": "hidden"}},
        )
        return {"ok": True, "status": "hidden"}

    @router.post("/admin/posts/{post_id}/unhide")
    async def unhide_post(post_id: str, admin=Depends(_admin)):
        # When unhiding, revert to approved (since release is by time, not status).
        r = await db.posts.update_one({"post_id": post_id}, {"$set": {"status": "approved"}, "$unset": {"hidden_at": "", "hidden_by": ""}})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Post not found")
        return {"ok": True, "status": "approved"}

    @router.post("/admin/replies/{reply_id}/hide")
    async def hide_reply(reply_id: str, admin=Depends(_admin)):
        r = await db.replies.update_one({"reply_id": reply_id}, {"$set": {"status": "hidden", "hidden_at": _now_iso(), "hidden_by": admin["email"]}})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Reply not found")
        await db.flags.update_many(
            {"target_kind": "reply", "target_id": reply_id, "resolved": False},
            {"$set": {"resolved": True, "resolved_at": _now_iso(), "resolved_by": admin["email"], "resolution": "hidden"}},
        )
        return {"ok": True, "status": "hidden"}

    @router.post("/admin/flags/{flag_id}/dismiss")
    async def dismiss_flag(flag_id: str, admin=Depends(_admin)):
        """Resolve a flag without hiding the target (false-positive)."""
        r = await db.flags.update_one(
            {"flag_id": flag_id, "resolved": False},
            {"$set": {"resolved": True, "resolved_at": _now_iso(), "resolved_by": admin["email"], "resolution": "dismissed"}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Flag not found or already resolved")
        return {"ok": True, "resolution": "dismissed"}

    return router
