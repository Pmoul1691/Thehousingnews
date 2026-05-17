"""Admin endpoints for the one-time public launch broadcast."""
import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException

from services.auth_helpers import get_current_user
from services.launch_broadcast import (
    build_launch_payload,
    render_launch_html,
    send_launch_broadcast,
)

logger = logging.getLogger(__name__)


def setup(db):
    router = APIRouter(prefix="/api/admin/launch", tags=["admin-launch"])

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        u = await get_current_user(db, session_token, authorization)
        if not u.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin only")
        return u

    @router.get("/preview")
    async def preview(session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
        await _admin(session_token, authorization)
        payload = await build_launch_payload(db)
        html = render_launch_html("Peter", payload)
        # Eligibility counts so the admin sees what "Send now" will do.
        total = await db.users.count_documents({"status": "approved", "suspended": {"$ne": True}})
        already = await db.email_dispatches.count_documents({"kind": "launch_broadcast"})
        return {
            "payload": payload,
            "html": html,
            "eligible_total": total,
            "already_sent": already,
            "remaining": max(0, total - already),
        }

    @router.post("/send")
    async def send(body: dict | None = None,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
        await _admin(session_token, authorization)
        body = body or {}
        force = bool(body.get("force"))
        confirm = (body.get("confirm") or "").strip().upper()
        if confirm != "LAUNCH":
            raise HTTPException(status_code=400, detail="Pass {'confirm':'LAUNCH'} to fire the broadcast.")
        result = await send_launch_broadcast(db, force=force)
        return result

    @router.post("/send-test")
    async def send_test(body: dict,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
        await _admin(session_token, authorization)
        email = (body or {}).get("email", "").strip()
        if "@" not in email:
            raise HTTPException(status_code=400, detail="A valid email is required")
        return await send_launch_broadcast(db, recipient_email=email)

    return router
