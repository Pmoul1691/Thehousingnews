"""Member profile routes (avatar, bio, market, 3 versioned public objectives)."""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field, field_validator

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    market: str = Field(min_length=2, max_length=120)
    bio: str = Field(max_length=280)
    avatar_path: Optional[str] = None
    objectives: List[str] = Field(min_length=3, max_length=3)

    @field_validator("objectives")
    @classmethod
    def trim_objectives(cls, v: List[str]):
        cleaned = [s.strip() for s in v if s and s.strip()]
        if len(cleaned) != 3:
            raise ValueError("Exactly 3 objectives required")
        for o in cleaned:
            if len(o) > 140:
                raise ValueError("Each objective must be 140 chars or fewer")
        return cleaned


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.get("")
    async def get_my_profile(user=Depends(_user)):
        prof = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
        return prof or {}

    @router.put("")
    async def upsert_profile(payload: ProfileUpdate, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        now_iso = datetime.now(timezone.utc).isoformat()

        existing = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
        objectives_version = (existing or {}).get("objectives_version", 0)
        prev_objectives = (existing or {}).get("objectives", [])
        if prev_objectives != payload.objectives:
            objectives_version += 1
            # Snapshot prior set
            if existing:
                await db.objective_history.insert_one({
                    "user_id": user["user_id"],
                    "version": existing.get("objectives_version", 0),
                    "objectives": prev_objectives,
                    "archived_at": now_iso,
                })

        doc = {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": payload.name,
            "market": payload.market,
            "bio": payload.bio,
            "avatar_path": payload.avatar_path or (existing or {}).get("avatar_path"),
            "objectives": payload.objectives,
            "objectives_version": objectives_version or 1,
            "updated_at": now_iso,
        }
        if not existing:
            doc["created_at"] = now_iso
            await db.profiles.insert_one(doc)
        else:
            await db.profiles.update_one({"user_id": user["user_id"]}, {"$set": doc})

        # Mirror name on user
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"name": payload.name}})

        doc.pop("_id", None)
        return doc

    @router.get("/{user_id}")
    async def get_profile(user_id: str, user=Depends(_user)):
        prof = await db.profiles.find_one({"user_id": user_id}, {"_id": 0})
        if not prof:
            raise HTTPException(status_code=404, detail="Profile not found")
        return prof

    return router
