"""Improvement suggestions — user-submitted, admin-triaged.

A small feedback widget sits floating on every page. Anyone (anonymous or
signed-in) can submit a short note. Admins review and mark status.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_user_admin

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = {"new", "reviewing", "done", "dismissed"}


class ImprovementCreate(BaseModel):
    text: str = Field(..., min_length=3, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=40)
    page_path: Optional[str] = Field(default=None, max_length=300)
    email: Optional[str] = Field(default=None, max_length=200)  # for anonymous submitters


class ImprovementStatus(BaseModel):
    status: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    router = APIRouter(prefix="/api", tags=["improvements"])

    async def _maybe_user(session_token, authorization):
        try:
            return await get_current_user(db, session_token, authorization)
        except HTTPException:
            return None

    @router.post("/improvements")
    async def submit_improvement(
        body: ImprovementCreate,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await _maybe_user(session_token, authorization)
        doc = {
            "id": f"imp_{uuid.uuid4().hex[:12]}",
            "text": body.text.strip(),
            "category": (body.category or "").strip() or None,
            "page_path": (body.page_path or "").strip() or None,
            "status": "new",
            "user_id": user["user_id"] if user else None,
            "submitter_name": user["name"] if user else None,
            "submitter_email": (user["email"] if user else (body.email or "").strip().lower() or None),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "resolved_at": None,
            "resolved_by": None,
        }
        await db.improvements.insert_one(doc)
        # Drop _id from echo (Mongo mutates the doc on insert)
        doc.pop("_id", None)
        return {"ok": True, "id": doc["id"]}

    # ── Admin ──────────────────────────────────────────────────────────
    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/admin/improvements")
    async def list_improvements(
        status: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=500),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        match = {}
        if status:
            if status not in ALLOWED_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status")
            match["status"] = status
        items = await db.improvements.find(match, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        # Counts by status (small fast aggregate)
        counts = {}
        for s in ALLOWED_STATUSES:
            counts[s] = await db.improvements.count_documents({"status": s})
        return {"items": items, "counts": counts}

    @router.post("/admin/improvements/{imp_id}/status")
    async def update_improvement_status(
        imp_id: str,
        body: ImprovementStatus,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        admin = await _admin(session_token, authorization)
        if body.status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        update = {
            "status": body.status,
            "updated_at": _now_iso(),
        }
        if body.status in ("done", "dismissed"):
            update["resolved_at"] = _now_iso()
            update["resolved_by"] = admin["email"]
        else:
            update["resolved_at"] = None
            update["resolved_by"] = None
        r = await db.improvements.update_one({"id": imp_id}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Improvement not found")
        return {"ok": True, "status": body.status}

    @router.delete("/admin/improvements/{imp_id}")
    async def delete_improvement(
        imp_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        r = await db.improvements.delete_one({"id": imp_id})
        if r.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Improvement not found")
        return {"ok": True}

    return router
