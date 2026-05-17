"""Member invite codes: 20 lifetime per member, 60-day expiry, one-time-use."""
import logging
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

MAX_LIFETIME = 20
EXPIRY_DAYS = 60
CODE_LEN = 8
CODE_ALPHABET = string.ascii_uppercase + string.digits
TOP_CONNECTOR_THRESHOLD = 3  # ≥3 approved referrals earns the badge


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def quarter_key(dt: Optional[datetime] = None) -> str:
    """Retained for backwards-compatibility with already-issued codes."""
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
    referrals = APIRouter(prefix="/api/referrals", tags=["referrals"])

    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    async def _approved(user):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")

    async def _stats_for(user_id: str) -> dict:
        """Aggregate sent/redeemed/approved counts for a member."""
        rows = await db.invite_codes.find(
            {"owner_user_id": user_id}, {"_id": 0},
        ).to_list(500)
        issued = len(rows)
        redeemed_ids = [r["redeemed_by_user_id"] for r in rows if r.get("redeemed_by_user_id")]
        redeemed = len(redeemed_ids)
        approved = 0
        if redeemed_ids:
            approved = await db.users.count_documents({
                "user_id": {"$in": redeemed_ids},
                "status": "approved",
            })
        return {
            "issued": issued,
            "redeemed": redeemed,
            "approved": approved,
            "remaining": max(0, MAX_LIFETIME - issued),
            "is_top_connector": approved >= TOP_CONNECTOR_THRESHOLD,
        }

    @invites.get("")
    async def list_my_invites(user=Depends(_user)):
        await _approved(user)
        rows = await db.invite_codes.find(
            {"owner_user_id": user["user_id"]},
            {"_id": 0},
        ).sort("created_at", -1).to_list(MAX_LIFETIME + 10)
        stats = await _stats_for(user["user_id"])
        return {
            "lifetime_cap": MAX_LIFETIME,
            "issued": stats["issued"],
            "redeemed": stats["redeemed"],
            "approved": stats["approved"],
            "remaining": stats["remaining"],
            "is_top_connector": stats["is_top_connector"],
            "items": rows,
        }

    @invites.post("")
    async def generate_my_invite(user=Depends(_user)):
        await _approved(user)
        already = await db.invite_codes.count_documents({"owner_user_id": user["user_id"]})
        if already >= MAX_LIFETIME:
            raise HTTPException(status_code=400, detail=f"You have used all {MAX_LIFETIME} of your invites")
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
            "quarter_key": quarter_key(),  # kept for legacy audits
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

    @referrals.get("/leaderboard")
    async def leaderboard(limit: int = 10):
        """Public-to-members leaderboard of Top Connectors. Returns members
        ranked by approved-referral count, descending. Hides ties by name.
        Members with 0 approvals are excluded so an empty leaderboard
        renders gracefully on a fresh platform."""
        pipeline = [
            {"$match": {"redeemed_by_user_id": {"$ne": None}}},
            {"$group": {"_id": "$owner_user_id", "redeemed": {"$sum": 1},
                        "redeemed_ids": {"$addToSet": "$redeemed_by_user_id"}}},
        ]
        rows = await db.invite_codes.aggregate(pipeline).to_list(500)
        if not rows:
            return {"items": [], "threshold": TOP_CONNECTOR_THRESHOLD}
        all_redeemed = [uid for r in rows for uid in r["redeemed_ids"]]
        approved_users = await db.users.find(
            {"user_id": {"$in": all_redeemed}, "status": "approved"},
            {"_id": 0, "user_id": 1},
        ).to_list(2000)
        approved_set = {u["user_id"] for u in approved_users}
        # Build leaderboard
        ranked: list[dict] = []
        for r in rows:
            approved_n = sum(1 for uid in r["redeemed_ids"] if uid in approved_set)
            if approved_n == 0:
                continue
            ranked.append({"user_id": r["_id"], "approved": approved_n, "redeemed": r["redeemed"]})
        ranked.sort(key=lambda x: (-x["approved"], -x["redeemed"]))
        ranked = ranked[:limit]
        owner_ids = [r["user_id"] for r in ranked]
        # Hydrate with profile bits
        profs = await db.profiles.find(
            {"user_id": {"$in": owner_ids}},
            {"_id": 0, "user_id": 1, "name": 1, "market": 1, "avatar_path": 1},
        ).to_list(200)
        pmap = {p["user_id"]: p for p in profs}
        items = []
        for r in ranked:
            p = pmap.get(r["user_id"]) or {}
            items.append({
                "user_id": r["user_id"],
                "name": p.get("name") or "Member",
                "market": p.get("market") or "",
                "avatar_path": p.get("avatar_path"),
                "approved": r["approved"],
                "redeemed": r["redeemed"],
                "is_top_connector": r["approved"] >= TOP_CONNECTOR_THRESHOLD,
            })
        return {"items": items, "threshold": TOP_CONNECTOR_THRESHOLD}

    @referrals.get("/me")
    async def my_referrals(user=Depends(_user)):
        await _approved(user)
        stats = await _stats_for(user["user_id"])
        # Resolve actual redeemers so the user sees who they invited.
        rows = await db.invite_codes.find(
            {"owner_user_id": user["user_id"], "redeemed_by_user_id": {"$ne": None}},
            {"_id": 0, "code": 1, "redeemed_by_user_id": 1, "redeemed_by_email": 1, "redeemed_at": 1},
        ).to_list(MAX_LIFETIME + 10)
        ids = [r["redeemed_by_user_id"] for r in rows]
        users = await db.users.find(
            {"user_id": {"$in": ids}},
            {"_id": 0, "user_id": 1, "name": 1, "status": 1},
        ).to_list(500) if ids else []
        umap = {u["user_id"]: u for u in users}
        invitees = []
        for r in rows:
            u = umap.get(r["redeemed_by_user_id"]) or {}
            invitees.append({
                "code": r["code"],
                "name": u.get("name") or r.get("redeemed_by_email", "Unknown"),
                "status": u.get("status") or "unknown",
                "redeemed_at": r.get("redeemed_at"),
            })
        invitees.sort(key=lambda x: x.get("redeemed_at") or "", reverse=True)
        return {**stats, "invitees": invitees, "threshold": TOP_CONNECTOR_THRESHOLD}

    return invites, public, referrals
