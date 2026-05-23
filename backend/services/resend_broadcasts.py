"""Resend Broadcasts API helpers.

Used for the daily Morning + Evening Brief sends to the newsletter
audience (14k+ contacts). A broadcast is a single API call that asks
Resend to fan out to an entire audience, handling per-contact
unsubscribe tokens, deliverability, and dashboard analytics for us.

Docs: https://resend.com/docs/api-reference/broadcasts

Why not transactional sends?
  At ~5 req/s rate limit, a 14k transactional fan-out would take ~47
  minutes and burn 14k API calls per brief. A single broadcast finishes
  in seconds and counts as one outbound action.
"""
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_API_BASE = "https://api.resend.com"
HTTP_TIMEOUT = 30


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }


def create_broadcast(
    audience_id: str,
    subject: str,
    html: str,
    from_email: str,
    from_name: str,
    reply_to: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """Create a draft broadcast targeting `audience_id`. Returns the
    Resend response (`{id, object: "broadcast"}`) or `{error, ...}`.
    """
    if not RESEND_API_KEY:
        return {"error": "RESEND_API_KEY missing", "skipped": True}
    payload = {
        "audience_id": audience_id,
        "from": f"{from_name} <{from_email}>" if from_name else from_email,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if name:
        payload["name"] = name
    try:
        r = requests.post(
            f"{RESEND_API_BASE}/broadcasts",
            json=payload,
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code >= 400:
            logger.error("resend broadcast create failed: %s %s", r.status_code, r.text[:300])
            return {"error": r.text, "status": r.status_code}
        return r.json()
    except Exception as e:
        logger.exception("resend broadcast create exception: %s", e)
        return {"error": str(e)}


def send_broadcast(broadcast_id: str, scheduled_at: Optional[str] = None) -> dict:
    """Trigger the broadcast. If `scheduled_at` (ISO-8601 UTC string) is given,
    Resend schedules the send for that timestamp instead of firing immediately.
    Returns Resend response dict or `{error, ...}`.
    """
    if not RESEND_API_KEY:
        return {"error": "RESEND_API_KEY missing", "skipped": True}
    body: dict = {}
    if scheduled_at:
        body["scheduled_at"] = scheduled_at
    try:
        r = requests.post(
            f"{RESEND_API_BASE}/broadcasts/{broadcast_id}/send",
            json=body,
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code >= 400:
            logger.error("resend broadcast send failed: %s %s", r.status_code, r.text[:300])
            return {"error": r.text, "status": r.status_code}
        return r.json()
    except Exception as e:
        logger.exception("resend broadcast send exception: %s", e)
        return {"error": str(e)}


def get_broadcast(broadcast_id: str) -> dict:
    if not RESEND_API_KEY:
        return {"error": "RESEND_API_KEY missing"}
    try:
        r = requests.get(
            f"{RESEND_API_BASE}/broadcasts/{broadcast_id}",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return {"error": r.text, "status": r.status_code}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def list_broadcasts(limit: int = 100) -> list:
    """List ALL broadcasts (drafts + scheduled + sent). Used by the
    /admin/drafts UI in Phase 2. Resend's GET /broadcasts is currently
    unpaginated so `limit` is a no-op but kept for forward compatibility.
    """
    if not RESEND_API_KEY:
        return []
    try:
        r = requests.get(
            f"{RESEND_API_BASE}/broadcasts",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("resend /broadcasts failed: %s %s", r.status_code, r.text[:200])
            return []
        return (r.json() or {}).get("data") or []
    except Exception as e:
        logger.warning("resend /broadcasts exception: %s", e)
        return []


def delete_broadcast(broadcast_id: str) -> dict:
    """Delete a draft broadcast (cannot delete sent ones)."""
    if not RESEND_API_KEY:
        return {"error": "RESEND_API_KEY missing"}
    try:
        r = requests.delete(
            f"{RESEND_API_BASE}/broadcasts/{broadcast_id}",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code >= 400:
            return {"error": r.text, "status": r.status_code}
        return r.json() if r.text else {"deleted": True}
    except Exception as e:
        return {"error": str(e)}
