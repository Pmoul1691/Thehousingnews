"""Member profile routes (avatar, bio, market, 3 versioned public objectives)."""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field, field_validator

from services.auth_helpers import get_current_user
from services.linkedin_import import fetch_linkedin_profile, LinkedInImportError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])


import re

class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    market: str = Field(min_length=2, max_length=120)
    bio: str = Field(max_length=280)
    avatar_path: Optional[str] = None
    objectives: List[str] = Field(min_length=3, max_length=3)
    linkedin_url: Optional[str] = Field(default=None, max_length=200)

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

    @field_validator("linkedin_url")
    @classmethod
    def normalize_linkedin(cls, v: Optional[str]):
        if not v:
            return None
        v = v.strip()
        # Accept a bare handle ("petermoulton") or a full URL.
        if not v:
            return None
        if re.match(r"^[a-zA-Z0-9\-]{2,80}$", v):
            return f"https://www.linkedin.com/in/{v.lower()}"
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        if not re.match(r"^https?://([a-z]+\.)?linkedin\.com/(in|company)/[^/?#\s]+", v, re.IGNORECASE):
            raise ValueError("LinkedIn URL must look like https://www.linkedin.com/in/your-handle")
        return v


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.get("")
    async def get_my_profile(user=Depends(_user)):
        prof = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not prof:
            return {}
        # Tell the frontend whether this is still a stub (created during
        # invite-claim) so it can render a "Finish setting up" banner
        # instead of treating the empty fields as a finished profile.
        is_stub = bool(prof.get("is_stub")) or (
            not (prof.get("market") or "").strip()
            and not [o for o in (prof.get("objectives") or []) if (o or "").strip()]
        )
        prof["is_complete"] = not is_stub
        prof["is_stub"] = is_stub
        return prof

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
            "linkedin_url": payload.linkedin_url,
            "is_stub": False,  # any successful upsert clears the stub flag
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

    @router.post("/linkedin-import")
    async def linkedin_import(payload: dict, user=Depends(_user)):
        """Look up a LinkedIn profile via EnrichLayer and return suggested
        fields the frontend can use to pre-fill the onboarding form.

        Also persists the raw experiences + education on the user's profile
        doc so we can render a "Career" block later without re-charging credits.

        Request body: {"linkedin_url": "https://www.linkedin.com/in/..."}
        """
        url = (payload or {}).get("linkedin_url") or ""
        url = url.strip()
        # Allow bare handles too
        if re.match(r"^[a-zA-Z0-9\-]{2,80}$", url):
            url = f"https://www.linkedin.com/in/{url.lower()}"
        if not url:
            # Fall back to whatever's already on the profile
            existing = await db.profiles.find_one(
                {"user_id": user["user_id"]}, {"_id": 0, "linkedin_url": 1},
            )
            url = (existing or {}).get("linkedin_url") or ""
        if not url:
            raise HTTPException(status_code=400, detail="No LinkedIn URL provided")

        try:
            enriched = fetch_linkedin_profile(url)
        except LinkedInImportError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        # Cache the enriched data on the profile (don't overwrite user-edited
        # fields like market/bio/objectives — those stay manual).
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.profiles.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "linkedin_url": enriched["linkedin_url"],
                "linkedin_data": {
                    "headline": enriched.get("headline"),
                    "occupation": enriched.get("occupation"),
                    "summary": enriched.get("summary"),
                    "location": enriched.get("location"),
                    "profile_pic_url": enriched.get("profile_pic_url"),
                    "experiences": enriched.get("experiences"),
                    "education": enriched.get("education"),
                    "synced_at": now_iso,
                },
            }},
            upsert=False,
        )

        # Suggested values for the onboarding form. The frontend decides
        # whether to apply them (we never overwrite without consent).
        return {
            "ok": True,
            "linkedin_url": enriched["linkedin_url"],
            "suggested": {
                "name": enriched.get("full_name"),
                "market": enriched.get("location"),
                "bio": (enriched.get("headline") or "")[:280],
                "avatar_url": enriched.get("profile_pic_url"),
            },
            "career": {
                "experiences": enriched.get("experiences") or [],
                "education": enriched.get("education") or [],
            },
        }

    @router.get("/{user_id}/essays")
    async def list_essays(user_id: str, user=Depends(_user)):
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not target or (target.get("suspended") and not user.get("is_admin")):
            return {"items": []}
        now_iso = datetime.now(timezone.utc).isoformat()
        cur = db.posts.find(
            {
                "user_id": user_id,
                "kind": "essay",
                "release_at": {"$lte": now_iso},
                "status": {"$nin": ["declined", "hidden"]},
            },
            {"_id": 0, "text": 0},  # exclude full body for the archive list
        ).sort("release_at", -1).limit(100)
        items = await cur.to_list(100)
        for it in items:
            it["is_pete_pick"] = bool(it.get("is_pete_pick"))
        return {"items": items}

    return router
