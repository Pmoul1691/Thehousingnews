"""Admin: promote/demote users to admin + lightweight user search.

Promoting a user sets `users.is_admin = True`. The canonical admin check is
`services.auth_helpers.is_user_admin(user)` which honours both the env-based
ADMIN_EMAILS list AND the runtime is_admin flag.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header, Query
from pydantic import BaseModel

from services.auth_helpers import get_current_user, is_user_admin, is_admin_email

logger = logging.getLogger(__name__)


class PromoteBody(BaseModel):
    is_admin: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])

    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/search")
    async def search_users(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=30, ge=1, le=100),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        q_norm = (q or "").strip()
        match = {"status": {"$ne": "needs_application"}}
        if q_norm:
            # Case-insensitive substring search across name & email
            import re as _re
            pat = _re.escape(q_norm)
            match["$or"] = [
                {"email": {"$regex": pat, "$options": "i"}},
                {"name": {"$regex": pat, "$options": "i"}},
            ]
        users = await db.users.find(
            match,
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "is_admin": 1, "status": 1, "suspended": 1},
        ).limit(limit).to_list(limit)
        items = []
        for u in users:
            items.append({
                "user_id": u["user_id"],
                "email": u.get("email") or "",
                "name": u.get("name") or "",
                "status": u.get("status") or "",
                "suspended": bool(u.get("suspended")),
                "is_admin": bool(u.get("is_admin")) or is_admin_email(u.get("email") or ""),
                "env_admin": is_admin_email(u.get("email") or ""),
            })
        items.sort(key=lambda r: (not r["is_admin"], r["email"].lower()))
        return {"items": items, "count": len(items)}

    @router.post("/{user_id}/promote")
    async def set_admin(
        user_id: str,
        body: PromoteBody,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        admin = await _admin(session_token, authorization)
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        # Refuse to demote yourself accidentally (env admins are safe but
        # makes the UX explicit for runtime-promoted users).
        if not body.is_admin and target.get("user_id") == admin.get("user_id"):
            raise HTTPException(status_code=400, detail="You cannot demote yourself")
        # Env admins cannot be demoted via this tool — they would auto-re-promote
        # on next login anyway. Surface a clear error instead.
        if not body.is_admin and is_admin_email(target.get("email") or ""):
            raise HTTPException(status_code=400, detail="This user is admin via ADMIN_EMAILS env config; cannot demote from the panel")
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_admin": bool(body.is_admin),
                "admin_changed_at": _now_iso(),
                "admin_changed_by": admin.get("email") or admin.get("user_id"),
            }},
        )
        return {"ok": True, "user_id": user_id, "is_admin": bool(body.is_admin)}

    return router
