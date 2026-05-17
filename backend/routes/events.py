"""Tiny client-fired analytics event collector.

The frontend POSTs a pageview event on every React Router navigation. The
event lands in `analytics_events`. No PII beyond user_id (when present)
and a random per-tab session_id.

Volume: with ~100 active members hitting ~20 pages a session, ~2k events/day.
Trivial at MongoDB scale.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["events"])


class PageView(BaseModel):
    path: str = Field(max_length=300)
    session_id: Optional[str] = Field(default=None, max_length=80)
    referrer: Optional[str] = Field(default=None, max_length=400)


def setup(db):
    @router.post("/pageview")
    async def pageview(
        ev: PageView,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        # Auth is best-effort — we want anonymous landing-page views logged too.
        user_id = None
        try:
            u = await get_current_user(db, session_token, authorization)
            user_id = u.get("user_id")
        except Exception:
            user_id = None

        # Strip any tracking params from path for cleaner aggregation
        path = (ev.path or "/").split("?")[0][:300]

        await db.analytics_events.insert_one({
            "id": f"ev_{uuid.uuid4().hex[:12]}",
            "kind": "pageview",
            "path": path,
            "user_id": user_id,
            "session_id": ev.session_id or f"anon_{uuid.uuid4().hex[:10]}",
            "referrer": (ev.referrer or "")[:400],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"ok": True}

    return router
