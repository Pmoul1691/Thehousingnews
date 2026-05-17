"""User-facing endpoints for managing Personal Access Tokens.

POST   /api/profile/pats         — create a new PAT (returns raw token ONCE)
GET    /api/profile/pats         — list the caller's PATs (sanitized)
DELETE /api/profile/pats/{pat_id}— revoke a PAT (soft delete)

Auth: standard session token. Approved members only — a PAT inherits the
caller's write permissions, so an un-approved user can't create one.
"""
from fastapi import APIRouter, Cookie, Header, HTTPException
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user
from services.pat_service import create_pat, public_pat_view
from datetime import datetime, timezone


class CreatePatBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


def setup(db):
    router = APIRouter(prefix="/api/pats", tags=["pats"])

    async def _approved_user(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Only approved members can create access tokens")
        return user

    @router.post("")
    async def create(
        body: CreatePatBody,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        user = await _approved_user(session_token, authorization)
        # Cap users at a reasonable number of live PATs to prevent runaway tokens.
        live_count = await db.pats.count_documents({"user_id": user["user_id"], "revoked_at": None})
        if live_count >= 10:
            raise HTTPException(status_code=400, detail="Revoke an existing token before creating another (max 10).")
        out = await create_pat(db, user["user_id"], body.name)
        return out

    @router.get("")
    async def list_pats(
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        user = await _approved_user(session_token, authorization)
        rows = await db.pats.find(
            {"user_id": user["user_id"]},
            {"_id": 0},
        ).sort("created_at", -1).to_list(50)
        return {"items": [public_pat_view(r) for r in rows]}

    @router.delete("/{pat_id}")
    async def revoke(
        pat_id: str,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        user = await _approved_user(session_token, authorization)
        res = await db.pats.update_one(
            {"id": pat_id, "user_id": user["user_id"], "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Token not found or already revoked")
        return {"ok": True, "revoked": pat_id}

    return router
