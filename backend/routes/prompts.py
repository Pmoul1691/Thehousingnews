"""Subject of the week: weekly writing prompts.

Lifecycle: one active prompt per Mon-Sun week. The scheduler advances on
Monday 8:30am CT (in services/scheduler.py).
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email, is_user_admin
from services.release_window import CHICAGO

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _week_start(dt: datetime) -> datetime:
    """Monday 00:00:00 of the dt's local Chicago week."""
    local = dt.astimezone(CHICAGO)
    monday = local - timedelta(days=local.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


class PromptCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=0, max_length=2000, default="")
    week_start: Optional[str] = None  # ISO date - if omitted, defaults to current week
    status: Optional[str] = "active"  # active|scheduled|past


class SuggestionCreate(BaseModel):
    text: str = Field(min_length=10, max_length=300)


def setup(db):
    public = APIRouter(prefix="/api/prompts", tags=["prompts"])
    admin_router = APIRouter(prefix="/api/admin/prompts", tags=["prompts"])

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

    async def _response_count(prompt_id: str) -> int:
        now_iso = _now_iso()
        return await db.posts.count_documents({
            "prompt_id": prompt_id,
            "release_at": {"$lte": now_iso},
            "status": {"$nin": ["declined", "hidden"]},
        })

    # ---- Public ----

    @public.get("/current")
    async def current_prompt():
        row = await db.prompts.find_one({"status": "active"}, {"_id": 0})
        if not row:
            return {}
        row["response_count"] = await _response_count(row["prompt_id"])
        return row

    @public.get("")
    async def list_prompts(limit: int = Query(20, le=50)):
        cur = db.prompts.find({"status": {"$in": ["active", "past"]}}, {"_id": 0}).sort("week_start", -1).limit(limit)
        items = await cur.to_list(limit)
        for it in items:
            it["response_count"] = await _response_count(it["prompt_id"])
        return {"items": items}

    @public.get("/{prompt_id}")
    async def get_prompt(prompt_id: str):
        row = await db.prompts.find_one({"prompt_id": prompt_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        # Pull responses (released posts linked to this prompt)
        now_iso = _now_iso()
        cur = db.posts.find(
            {"prompt_id": prompt_id, "release_at": {"$lte": now_iso}, "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0, "text": 0},
        ).sort("release_at", -1).limit(100)
        responses = await cur.to_list(100)

        if responses:
            user_ids = list({p["user_id"] for p in responses})
            profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
            pmap = {p["user_id"]: p for p in profiles}
            for p in responses:
                prof = pmap.get(p["user_id"]) or {}
                p["author"] = {
                    "user_id": p["user_id"],
                    "name": prof.get("name") or "Member",
                    "market": prof.get("market"),
                    "avatar_path": prof.get("avatar_path"),
                }
        row["responses"] = responses
        row["response_count"] = len(responses)
        return row

    # ---- Member suggestions ----

    @public.post("/suggestions")
    async def submit_suggestion(payload: SuggestionCreate, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        doc = {
            "suggestion_id": f"sug_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
            "user_name": user.get("name") or "Member",
            "text": payload.text.strip(),
            "status": "open",
            "created_at": _now_iso(),
        }
        await db.prompt_suggestions.insert_one(doc)
        doc.pop("_id", None)
        return doc

    # ---- Admin ----

    @admin_router.post("")
    async def create_prompt(payload: PromptCreate, admin=Depends(_admin)):
        now = datetime.now(timezone.utc)
        if payload.week_start:
            try:
                ws_dt = datetime.fromisoformat(payload.week_start.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid week_start")
        else:
            ws_dt = _week_start(now)
        ws_dt = ws_dt.astimezone(CHICAGO).replace(hour=0, minute=0, second=0, microsecond=0)
        we_dt = ws_dt + timedelta(days=7)
        prompt_id = f"prompt_{uuid.uuid4().hex[:12]}"
        # If this prompt is active, demote any existing active prompt to past
        status = payload.status or "active"
        if status == "active":
            await db.prompts.update_many({"status": "active"}, {"$set": {"status": "past"}})
        doc = {
            "prompt_id": prompt_id,
            "title": payload.title.strip(),
            "body": (payload.body or "").strip(),
            "week_start": ws_dt.astimezone(timezone.utc).isoformat(),
            "week_end": we_dt.astimezone(timezone.utc).isoformat(),
            "status": status,
            "created_at": _now_iso(),
            "created_by": admin["email"],
        }
        await db.prompts.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @admin_router.patch("/{prompt_id}")
    async def edit_prompt(prompt_id: str, payload: PromptCreate, admin=Depends(_admin)):
        row = await db.prompts.find_one({"prompt_id": prompt_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        update = {"title": payload.title.strip(), "body": (payload.body or "").strip()}
        if payload.status and payload.status in ("active", "scheduled", "past"):
            update["status"] = payload.status
            if payload.status == "active":
                await db.prompts.update_many(
                    {"status": "active", "prompt_id": {"$ne": prompt_id}},
                    {"$set": {"status": "past"}},
                )
        await db.prompts.update_one({"prompt_id": prompt_id}, {"$set": update})
        return {"ok": True}

    @admin_router.delete("/{prompt_id}")
    async def delete_prompt(prompt_id: str, admin=Depends(_admin)):
        r = await db.prompts.delete_one({"prompt_id": prompt_id})
        if r.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"ok": True}

    @admin_router.get("/suggestions")
    async def list_suggestions(status: str = "open", admin=Depends(_admin)):
        cur = db.prompt_suggestions.find({"status": status}, {"_id": 0}).sort("created_at", -1).limit(200)
        items = await cur.to_list(200)
        return {"items": items}

    @admin_router.post("/suggestions/{suggestion_id}/accept")
    async def accept_suggestion(suggestion_id: str, admin=Depends(_admin)):
        row = await db.prompt_suggestions.find_one({"suggestion_id": suggestion_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        await db.prompt_suggestions.update_one(
            {"suggestion_id": suggestion_id},
            {"$set": {"status": "accepted", "reviewed_at": _now_iso(), "reviewed_by": admin["email"]}},
        )
        return {"ok": True, "text": row["text"]}

    @admin_router.post("/suggestions/{suggestion_id}/reject")
    async def reject_suggestion(suggestion_id: str, admin=Depends(_admin)):
        r = await db.prompt_suggestions.update_one(
            {"suggestion_id": suggestion_id},
            {"$set": {"status": "rejected", "reviewed_at": _now_iso(), "reviewed_by": admin["email"]}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        return {"ok": True}

    return public, admin_router


async def advance_weekly_prompt(db):
    """Scheduler job: every Monday 8:30am CT mark the active prompt as `past`
    and promote the next `scheduled` prompt whose `week_start` <= now to `active`.
    If no scheduled prompt is queued, no-op (leaves the slot empty for admin to set)."""
    now_iso = _now_iso()
    await db.prompts.update_many({"status": "active"}, {"$set": {"status": "past"}})
    nxt = await db.prompts.find_one(
        {"status": "scheduled", "week_start": {"$lte": now_iso}},
        {"_id": 0},
        sort=[("week_start", 1)],
    )
    if nxt:
        await db.prompts.update_one({"prompt_id": nxt["prompt_id"]}, {"$set": {"status": "active"}})
        return {"promoted": nxt["prompt_id"]}
    return {"promoted": None}
