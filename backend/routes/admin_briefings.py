"""Admin endpoints for the Morning + Evening housing-news briefs.

- GET  /api/admin/briefings/preview?kind=morning|evening  → dry-run dump
- POST /api/admin/briefings/send?kind=morning|evening     → fire immediately
- POST /api/admin/briefings/send-test?kind=...&email=...  → send to one inbox
"""
from fastapi import APIRouter, Cookie, Header, HTTPException, Query

from services.auth_helpers import get_current_user, is_admin_email, is_user_admin
from services.briefings import build_brief_payload, send_brief
from services.brevo import send_brief_email


def setup(db):
    router = APIRouter(prefix="/api/admin/briefings", tags=["admin-briefings"])

    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/preview")
    async def preview(
        kind: str = Query(default="morning", regex="^(morning|evening)$"),
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Dry-run: shows exactly what content + how many recipients the brief
        would target right now, without sending."""
        await _admin(session_token, authorization)
        payload = await build_brief_payload(db, kind)
        recipients_total = await db.users.count_documents({
            "status": {"$in": ["approved", "invited"]},
            "suspended": {"$ne": True},
            "brief_optout": {"$ne": True},
        })
        return {
            "kind": kind,
            "recipients_total": recipients_total,
            "articles": [
                {
                    "title": a.get("title"),
                    "publisher": (a.get("publisher") or {}).get("name"),
                    "url": a.get("original_url"),
                    "published_at": a.get("published_at"),
                }
                for a in (payload.get("articles") or [])
            ],
            "podcast": (
                {
                    "title": payload["podcast"].get("title"),
                    "episode": (payload["podcast"].get("latest_episode") or {}).get("title"),
                } if payload.get("podcast") else None
            ),
            "trending": payload.get("trending"),
            "essay": (
                {
                    "title": payload["essay"].get("title"),
                    "author": (payload["essay"].get("author") or {}).get("name"),
                } if payload.get("essay") else None
            ),
        }

    @router.post("/send")
    async def send_now(
        kind: str = Query(default="morning", regex="^(morning|evening)$"),
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Fire the brief immediately to all approved + invited members."""
        await _admin(session_token, authorization)
        return await send_brief(db, kind)

    @router.post("/send-test")
    async def send_test(
        kind: str = Query(default="morning", regex="^(morning|evening)$"),
        email: str = Query(..., min_length=3, max_length=200),
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Send a single test brief to one inbox without recording dispatch rows
        or affecting the real member audience. Useful for previewing the HTML."""
        user = await _admin(session_token, authorization)
        payload = await build_brief_payload(db, kind)
        if not payload["articles"]:
            return {"sent": 0, "reason": "no_articles", "kind": kind}
        try:
            from services.release_window import CHICAGO
            from datetime import datetime as _dt
            today_label = _dt.now(CHICAGO).strftime("%a %b %-d")
        except Exception:
            from datetime import datetime as _dt
            today_label = _dt.utcnow().strftime("%a %b %-d")
        label_word = "Morning" if kind == "morning" else "Evening"
        subject = f"[TEST] Housing News · {label_word} Brief · {today_label}"
        result = send_brief_email(
            email,
            user.get("name") or "Test",
            subject=subject,
            kind=kind,
            payload=payload,
            dispatch_id=None,  # no tracking on test sends
        )
        return {"sent_to": email, "kind": kind, "subject": subject, "brevo": result}

    return router
