"""Admin endpoints for Resend broadcasts: list, create, edit, send, delete.

Powers the `/admin/drafts` page. Lets the operator compose a newsletter
in the dashboard, save it as a Resend draft, preview it, schedule it
for a future time, or fire it immediately to any audience.

Endpoints (all `/api/admin/*`, admin-gated):
  GET    /broadcasts                     → list (with optional ?status= filter)
  GET    /broadcasts/{id}                → get one
  POST   /broadcasts                     → create draft
  PATCH  /broadcasts/{id}                → update draft fields
  POST   /broadcasts/{id}/send           → send now or schedule
  DELETE /broadcasts/{id}                → delete
  GET    /broadcasts/audiences           → list audiences (dropdown)
  GET    /broadcasts/defaults            → default from/sender values
"""
import asyncio
import os
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_user_admin
from services.brevo import BRIEF_SENDER_EMAIL, BRIEF_SENDER_NAME
from services.brevo_contacts import list_brevo_lists
from services.resend_broadcasts import (
    create_broadcast,
    delete_broadcast,
    get_broadcast,
    list_broadcasts,
    send_broadcast,
)

try:
    import requests
except ImportError:
    requests = None

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_API_BASE = "https://api.resend.com"


class BroadcastCreate(BaseModel):
    audience_id: str = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=200)
    html: str = Field(min_length=1)
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    name: Optional[str] = None


class BroadcastUpdate(BaseModel):
    audience_id: Optional[str] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    name: Optional[str] = None


class BroadcastSend(BaseModel):
    scheduled_at: Optional[str] = None  # ISO-8601 UTC string; if absent, send now


def _patch_broadcast(broadcast_id: str, fields: dict) -> dict:
    """PATCH /broadcasts/{id} via the Resend API. Mirrors create_broadcast's
    error-shape convention so the route can return it directly."""
    if not RESEND_API_KEY:
        return {"error": "RESEND_API_KEY missing", "skipped": True}
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.patch(
            f"{RESEND_API_BASE}/broadcasts/{broadcast_id}",
            json=fields,
            headers=headers,
            timeout=30,
        )
        if r.status_code >= 400:
            return {"error": r.text, "status": r.status_code}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def setup(db):
    router = APIRouter(prefix="/api/admin/broadcasts", tags=["admin-broadcasts"])

    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("")
    async def list_all(
        status: Optional[str] = Query(default=None, regex="^(draft|queued|sending|sent|cancelled)?$"),
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        items = await asyncio.to_thread(list_broadcasts, 100)
        if status:
            items = [b for b in items if (b.get("status") or "").lower() == status]
        # Sort: newest first. Resend returns `created_at` as ISO string.
        items.sort(key=lambda b: b.get("created_at") or "", reverse=True)
        return {"data": items, "count": len(items)}

    @router.get("/audiences")
    async def audiences(
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Audience list for the create/edit dropdown."""
        await _admin(session_token, authorization)
        items = await asyncio.to_thread(list_brevo_lists)
        return {"data": items, "default_id": os.environ.get(
            "RESEND_BRIEF_AUDIENCE_ID",
            "e680753d-e3c1-40db-9286-1418fc25bf63",
        )}

    @router.get("/defaults")
    async def defaults(
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Default sender + audience to pre-fill the new-draft form."""
        await _admin(session_token, authorization)
        return {
            "from_email": BRIEF_SENDER_EMAIL,
            "from_name": BRIEF_SENDER_NAME,
            "reply_to": BRIEF_SENDER_EMAIL,
            "default_audience_id": os.environ.get(
                "RESEND_BRIEF_AUDIENCE_ID",
                "e680753d-e3c1-40db-9286-1418fc25bf63",
            ),
        }

    @router.get("/{broadcast_id}")
    async def get_one(
        broadcast_id: str,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        b = await asyncio.to_thread(get_broadcast, broadcast_id)
        if not b or b.get("error"):
            raise HTTPException(status_code=404, detail=(b or {}).get("error", "not found"))
        return b

    @router.post("")
    async def create(
        payload: BroadcastCreate,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        result = await asyncio.to_thread(
            create_broadcast,
            payload.audience_id,
            payload.subject,
            payload.html,
            payload.from_email or BRIEF_SENDER_EMAIL,
            payload.from_name or BRIEF_SENDER_NAME,
            payload.reply_to or BRIEF_SENDER_EMAIL,
            payload.name,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.patch("/{broadcast_id}")
    async def update(
        broadcast_id: str,
        payload: BroadcastUpdate,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        # Translate from our field names to Resend's exact API field names.
        fields: dict = {}
        if payload.audience_id is not None:
            fields["audience_id"] = payload.audience_id
        if payload.subject is not None:
            fields["subject"] = payload.subject
        if payload.html is not None:
            fields["html"] = payload.html
        if payload.reply_to is not None:
            fields["reply_to"] = payload.reply_to
        if payload.name is not None:
            fields["name"] = payload.name
        if payload.from_email is not None or payload.from_name is not None:
            from_email = payload.from_email or BRIEF_SENDER_EMAIL
            from_name = payload.from_name or BRIEF_SENDER_NAME
            fields["from"] = f"{from_name} <{from_email}>" if from_name else from_email
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = await asyncio.to_thread(_patch_broadcast, broadcast_id, fields)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.post("/{broadcast_id}/send")
    async def send_one(
        broadcast_id: str,
        payload: BroadcastSend,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        result = await asyncio.to_thread(send_broadcast, broadcast_id, payload.scheduled_at)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        # Record locally so the brief_broadcasts collection picks up
        # operator-initiated sends too (not just scheduler-driven ones).
        try:
            await db.brief_broadcasts.insert_one({
                "broadcast_id": broadcast_id,
                "kind": "manual",
                "scheduled_at": payload.scheduled_at,
                "created_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
            })
        except Exception:
            pass
        return result

    @router.delete("/{broadcast_id}")
    async def delete_one(
        broadcast_id: str,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        result = await asyncio.to_thread(delete_broadcast, broadcast_id)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    return router
