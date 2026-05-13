"""Member invite codes: 2 per quarter, 60-day expiry, one-time-use."""
import logging
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

MAX_PER_QUARTER = 2
EXPIRY_DAYS = 60
CODE_LEN = 8
CODE_ALPHABET = string.ascii_uppercase + string.digits


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def quarter_key(dt: Optional[datetime] = None) -> str:
    d = dt or _now()
    q = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{q}"


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


class CodeValidate(BaseModel):
    code: str = Field(min_length=4, max_length=32)


def setup(db):
    invites = APIRouter(prefix="/api/me/invites", tags=["invites"])
    public = APIRouter(prefix="/api/invite", tags=["invites"])

    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    async def _approved(user):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")

    @invites.get("")
    async def list_my_invites(user=Depends(_user)):
        await _approved(user)
        qk = quarter_key()
        rows = await db.invite_codes.find(
            {"owner_user_id": user["user_id"], "quarter_key": qk},
            {"_id": 0},
        ).sort("created_at", -1).to_list(20)
        used = sum(1 for r in rows if r.get("redeemed_by_user_id"))
        return {
            "quarter": qk,
            "max_per_quarter": MAX_PER_QUARTER,
            "issued": len(rows),
            "redeemed": used,
            "remaining": max(0, MAX_PER_QUARTER - len(rows)),
            "items": rows,
        }

    @invites.post("")
    async def generate_my_invite(user=Depends(_user)):
        await _approved(user)
        qk = quarter_key()
        already = await db.invite_codes.count_documents({"owner_user_id": user["user_id"], "quarter_key": qk})
        if already >= MAX_PER_QUARTER:
            raise HTTPException(status_code=400, detail=f"You have used your {MAX_PER_QUARTER} invites for {qk}")
        now = _now()
        # Generate a unique code (retry on collision)
        for _ in range(8):
            code = _new_code()
            exists = await db.invite_codes.find_one({"code": code}, {"_id": 0, "code": 1})
            if not exists:
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate code")
        row = {
            "code": code,
            "owner_user_id": user["user_id"],
            "owner_name": user.get("name") or "Member",
            "quarter_key": qk,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=EXPIRY_DAYS)).isoformat(),
            "redeemed_by_user_id": None,
            "redeemed_by_email": None,
            "redeemed_at": None,
        }
        await db.invite_codes.insert_one(row)
        row.pop("_id", None)
        return row

    @invites.delete("/{code}")
    async def revoke_my_invite(code: str, user=Depends(_user)):
        await _approved(user)
        existing = await db.invite_codes.find_one({"code": code, "owner_user_id": user["user_id"]}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Code not found")
        if existing.get("redeemed_by_user_id"):
            raise HTTPException(status_code=400, detail="Code already redeemed")
        await db.invite_codes.delete_one({"code": code, "owner_user_id": user["user_id"]})
        return {"ok": True}

    @public.post("/validate")
    async def validate_code(payload: CodeValidate):
        """Public: validate an invite code without redeeming it. Used by the apply form."""
        code = payload.code.strip().upper()
        row = await db.invite_codes.find_one({"code": code}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Invite code not found")
        if row.get("redeemed_by_user_id"):
            raise HTTPException(status_code=400, detail="This invite has already been used")
        if row.get("expires_at") and row["expires_at"] < _now_iso():
            raise HTTPException(status_code=400, detail="This invite has expired")
        return {
            "ok": True,
            "owner_name": row.get("owner_name") or "A member",
            "expires_at": row.get("expires_at"),
        }

    return invites, public
