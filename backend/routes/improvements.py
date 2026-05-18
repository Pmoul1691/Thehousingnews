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
from services.brevo import send_email

logger = logging.getLogger(__name__)


def _esc(s: str) -> str:
    """Minimal HTML escape for the user-supplied text we echo back in emails."""
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _send_thank_you(email: str, name: str, text: str) -> None:
    if not email:
        return
    quote = _esc(text)[:600]
    if len(text) > 600:
        quote += "…"
    html = f"""
<p>Hi {_esc(name) or 'there'},</p>
<p>Thanks for the suggestion — we read every note personally.</p>
<blockquote style="margin:18px 0;padding:12px 16px;border-left:3px solid #B89F3D;background:#F8F2DD;font-family:Georgia,serif;color:#2C2410;white-space:pre-wrap">{quote}</blockquote>
<p>We'll get back to you if it goes somewhere useful.</p>
<p style="font-size:12px;color:#7A6E4F">— The editors at The Housing News</p>
"""
    try:
        result = send_email(email, name or email, "Got your note — thanks", html, tags=["thn_improvement", "received"])
        logger.info("improvement thank-you sent to %s: %s", email, (result or {}).get("messageId") or result)
    except Exception:
        logger.exception("thank-you send failed for %s", email)


def _send_status_update(email: str, name: str, text: str, status: str) -> None:
    if not email or status not in ("reviewing", "done"):
        return
    quote = _esc(text)[:600]
    if len(text) > 600:
        quote += "…"
    if status == "reviewing":
        subject = "We're looking at your suggestion"
        line = "<p>Quick update — we're actively reviewing this. No action needed on your end.</p>"
    else:
        subject = "We shipped your suggestion"
        line = "<p>Good news — we acted on this. Thanks for taking the time to write in.</p>"
    html = f"""
<p>Hi {_esc(name) or 'there'},</p>
{line}
<blockquote style="margin:18px 0;padding:12px 16px;border-left:3px solid #B89F3D;background:#F8F2DD;font-family:Georgia,serif;color:#2C2410;white-space:pre-wrap">{quote}</blockquote>
<p style="font-size:12px;color:#7A6E4F">— The editors at The Housing News</p>
"""
    try:
        result = send_email(email, name or email, subject, html, tags=["thn_improvement", status])
        logger.info("improvement %s update sent to %s: %s", status, email, (result or {}).get("messageId") or result)
    except Exception:
        logger.exception("status-update send failed for %s (%s)", email, status)


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
        # Fire-and-forget thank-you email if we have an address to reply to.
        if doc.get("submitter_email"):
            _send_thank_you(doc["submitter_email"], doc.get("submitter_name") or "", doc["text"])
        return {"ok": True, "id": doc["id"]}

    # ── Admin ──────────────────────────────────────────────────────────
    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/admin/improvements/counts")
    async def improvements_counts(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        counts = {}
        for s in ALLOWED_STATUSES:
            counts[s] = await db.improvements.count_documents({"status": s})
        return {"counts": counts}

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
        # Read the current doc so we can: (a) detect a real status change and
        # (b) email the submitter when we move them to reviewing/done.
        before = await db.improvements.find_one({"id": imp_id}, {"_id": 0})
        if not before:
            raise HTTPException(status_code=404, detail="Improvement not found")

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
        await db.improvements.update_one({"id": imp_id}, {"$set": update})

        # Notify submitter on meaningful status transitions only (skip same-state
        # re-marks and the dismissed path — we don't tell people we ignored them).
        if (
            body.status != before.get("status")
            and body.status in ("reviewing", "done")
            and before.get("submitter_email")
        ):
            _send_status_update(
                before["submitter_email"],
                before.get("submitter_name") or "",
                before.get("text") or "",
                body.status,
            )
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
