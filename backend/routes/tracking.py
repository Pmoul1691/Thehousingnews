"""Email tracking endpoints: 1x1 open pixel + click redirect.

Both endpoints are public (no auth) since they run from email clients.
Each event row is idempotent-on-insert per (dispatch_id, kind, ip+ua hash short window).
"""
import logging
import base64
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/track", tags=["tracking"])

# Minimal 1x1 transparent GIF (43 bytes)
_PIXEL_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return req.client.host if req.client else ""


def setup(db):
    @router.get("/open/{dispatch_id}.gif")
    async def track_open(dispatch_id: str, request: Request):
        try:
            event = {
                "kind": "open",
                "dispatch_id": dispatch_id,
                "ip": _client_ip(request),
                "user_agent": request.headers.get("user-agent", "")[:300],
                "created_at": _now_iso(),
            }
            await db.email_events.insert_one(event)
            # Mark first_opened_at on the dispatch row if it exists
            await db.email_dispatches.update_one(
                {"dispatch_id": dispatch_id, "first_opened_at": None},
                {"$set": {"first_opened_at": event["created_at"]}},
            )
        except Exception:
            logger.exception("track_open failed")
        # Always return the pixel even on internal failure
        return Response(
            content=_PIXEL_GIF,
            media_type="image/gif",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @router.get("/click/{dispatch_id}")
    async def track_click(dispatch_id: str, to: Optional[str], request: Request):
        target = (to or "").strip()
        # Reject empty or non-http(s) targets to prevent open-redirect abuse
        if not target or not (target.startswith("http://") or target.startswith("https://")):
            return Response(content="Invalid redirect", status_code=400)
        try:
            event = {
                "kind": "click",
                "dispatch_id": dispatch_id,
                "target_url": target,
                "ip": _client_ip(request),
                "user_agent": request.headers.get("user-agent", "")[:300],
                "created_at": _now_iso(),
            }
            await db.email_events.insert_one(event)
            await db.email_dispatches.update_one(
                {"dispatch_id": dispatch_id, "first_clicked_at": None},
                {"$set": {"first_clicked_at": event["created_at"]}},
            )
        except Exception:
            logger.exception("track_click failed")
        return RedirectResponse(url=target, status_code=302)

    return router
