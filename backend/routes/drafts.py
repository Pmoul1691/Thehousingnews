"""Draft save: one in-progress draft per user, either kind."""
import logging
from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftSave(BaseModel):
    kind: Literal["post", "essay"] = "post"
    text: str = Field(default="", max_length=50000)
    title: Optional[str] = Field(default=None, max_length=160)
    subtitle: Optional[str] = Field(default=None, max_length=240)
    image_path: Optional[str] = None
    media: Optional[list] = None
    scheduled_at: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.get("/mine")
    async def my_draft(user=Depends(_user)):
        d = await db.drafts.find_one({"user_id": user["user_id"]}, {"_id": 0})
        return d or {}

    @router.put("/mine")
    async def save_draft(payload: DraftSave, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        doc = {
            "user_id": user["user_id"],
            "kind": payload.kind,
            "text": payload.text,
            "title": payload.title,
            "subtitle": payload.subtitle,
            "image_path": payload.image_path,
            "media": payload.media or [],
            "scheduled_at": payload.scheduled_at,
            "updated_at": _now_iso(),
        }
        await db.drafts.update_one(
            {"user_id": user["user_id"]},
            {"$set": doc, "$setOnInsert": {"created_at": _now_iso()}},
            upsert=True,
        )
        return doc

    @router.delete("/mine")
    async def clear_draft(user=Depends(_user)):
        await db.drafts.delete_one({"user_id": user["user_id"]})
        return {"ok": True}

    return router
