"""Membership applications + admin queue."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email
from services.brevo import (
    send_application_received,
    send_application_accepted,
    send_application_declined,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["applications"])


class ApplicationCreate(BaseModel):
    why_joining: str = Field(min_length=20, max_length=600)
    current_role: str = Field(min_length=2, max_length=200)
    market: str = Field(min_length=2, max_length=120)
    years_in_real_estate: str = Field(min_length=1, max_length=40)
    invite_code: Optional[str] = Field(default=None, max_length=32)


class ApplicationReview(BaseModel):
    note: Optional[str] = None


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

    @router.post("")
    async def submit_application(payload: ApplicationCreate, user=Depends(_user)):
        if user.get("status") == "approved":
            return {"status": "approved", "note": "already approved"}
        # Upsert by user_id
        existing = await db.applications.find_one({"user_id": user["user_id"]}, {"_id": 0})
        now_iso = datetime.now(timezone.utc).isoformat()
        if existing and existing.get("status") in ("pending", "approved"):
            return {"status": existing["status"], "application_id": existing["application_id"]}
        app_id = f"app_{uuid.uuid4().hex[:12]}"

        # Rate-limit: at most one application per email per 24 hours.
        # The user might also re-submit if their previous app was declined; we allow
        # that only after 24h.
        since_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        recent = await db.applications.count_documents({
            "email": user["email"],
            "created_at": {"$gte": since_iso},
        })
        if recent > 0:
            raise HTTPException(status_code=429, detail="You can only submit one application per 24 hours")

        # Validate + redeem optional invite code
        invited_by_user_id = None
        invited_by_name = None
        if payload.invite_code:
            code = payload.invite_code.strip().upper()
            row = await db.invite_codes.find_one({"code": code}, {"_id": 0})
            if not row:
                raise HTTPException(status_code=400, detail="Invite code not found")
            if row.get("redeemed_by_user_id"):
                raise HTTPException(status_code=400, detail="This invite has already been used")
            if row.get("expires_at") and row["expires_at"] < now_iso:
                raise HTTPException(status_code=400, detail="This invite has expired")
            # Reserve it atomically
            redeem = await db.invite_codes.update_one(
                {"code": code, "redeemed_by_user_id": None},
                {"$set": {
                    "redeemed_by_user_id": user["user_id"],
                    "redeemed_by_email": user["email"],
                    "redeemed_at": now_iso,
                }},
            )
            if redeem.modified_count != 1:
                raise HTTPException(status_code=400, detail="This invite has already been used")
            invited_by_user_id = row.get("owner_user_id")
            invited_by_name = row.get("owner_name")

        doc = {
            "application_id": app_id,
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "why_joining": payload.why_joining,
            "current_role": payload.current_role,
            "market": payload.market,
            "years_in_real_estate": payload.years_in_real_estate,
            "invited_by_user_id": invited_by_user_id,
            "invited_by_name": invited_by_name,
            "status": "pending",
            "created_at": now_iso,
            "reviewed_at": None,
            "reviewed_by": None,
        }
        await db.applications.insert_one(doc)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"status": "pending", "invited_by_user_id": invited_by_user_id}})
        send_application_received(user["email"], user["name"])
        return {"status": "pending", "application_id": app_id}

    @router.get("/mine")
    async def my_application(user=Depends(_user)):
        existing = await db.applications.find_one({"user_id": user["user_id"]}, {"_id": 0})
        return existing or {}

    @router.get("")
    async def list_applications(status: str = "pending", admin=Depends(_admin)):
        cur = db.applications.find({"status": status}, {"_id": 0}).sort("created_at", -1)
        items: List[dict] = await cur.to_list(500)
        return {"items": items}

    @router.post("/{application_id}/approve")
    async def approve(application_id: str, payload: ApplicationReview, admin=Depends(_admin)):
        app_doc = await db.applications.find_one({"application_id": application_id}, {"_id": 0})
        if not app_doc:
            raise HTTPException(status_code=404, detail="Application not found")
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.applications.update_one(
            {"application_id": application_id},
            {"$set": {"status": "approved", "reviewed_at": now_iso, "reviewed_by": admin["email"], "review_note": payload.note}},
        )
        await db.users.update_one({"user_id": app_doc["user_id"]}, {"$set": {"status": "approved"}})
        send_application_accepted(app_doc["email"], app_doc["name"], os.environ.get("APP_PUBLIC_URL", ""))
        return {"ok": True}

    @router.post("/{application_id}/decline")
    async def decline(application_id: str, payload: ApplicationReview, admin=Depends(_admin)):
        app_doc = await db.applications.find_one({"application_id": application_id}, {"_id": 0})
        if not app_doc:
            raise HTTPException(status_code=404, detail="Application not found")
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.applications.update_one(
            {"application_id": application_id},
            {"$set": {"status": "declined", "reviewed_at": now_iso, "reviewed_by": admin["email"], "review_note": payload.note}},
        )
        await db.users.update_one({"user_id": app_doc["user_id"]}, {"$set": {"status": "declined"}})
        send_application_declined(app_doc["email"], app_doc["name"])
        return {"ok": True}

    return router
