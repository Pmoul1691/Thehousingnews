"""Public endpoint: let prospective members check if their Ultradian Partners /
Ultradia.io email is already comped before they sign in. Rate-limited per IP to
prevent the bridge being used as an email-existence oracle.

Also exposes an authed /api/me/entitlement endpoint that surfaces the same
comped-status info for the signed-in user, used by the Profile page badge.
"""
import logging
import re
import time
from collections import defaultdict, deque
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request

from services.cross_property import get_user_status
from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# In-memory rolling window: 10 requests / IP / 60 seconds. Process-local, fine
# for a single backend pod; the bridge itself also rate-limits.
_RATE_BUCKET = defaultdict(deque)
_RATE_LIMIT = 10
_RATE_WINDOW = 60.0


def _rate_ok(ip: str) -> bool:
    now = time.time()
    bucket = _RATE_BUCKET[ip]
    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT:
        return False
    bucket.append(now)
    return True


def setup(db):
    router = APIRouter(tags=["partners"])

    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.get("/api/partners/check")
    async def check(request: Request, email: str = Query(..., min_length=3, max_length=200)):
        ip = request.client.host if request.client else "unknown"
        if not _rate_ok(ip):
            raise HTTPException(status_code=429, detail="Too many checks. Try again in a minute.")

        email = email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email address.")

        bridge = get_user_status(email)
        comped = bridge.get("network_grant") == "auto"
        exists = bool(bridge.get("exists"))
        # The bridge may use a few possible keys for the renewal date depending
        # on the upstream property. Accept whichever is present, in priority order.
        renews_at = (
            bridge.get("renews_at")
            or bridge.get("current_period_end")
            or bridge.get("next_billing_date")
            or bridge.get("expires_at")
        )
        return {
            "email": email,
            "comped": comped,
            "exists": exists,
            "tier": bridge.get("subscription_tier") if exists else None,
            "name": bridge.get("name") if exists else None,
            "renews_at": renews_at if exists else None,
            "property": bridge.get("property") or bridge.get("source"),  # e.g. "ultradianpartners" | "ultradia.io"
        }

    @router.get("/api/me/entitlement")
    async def my_entitlement(user=Depends(_user)):
        """Authed: return the signed-in user's comp/supporter status for the
        Profile page badge. Combines (a) live bridge call by email for partner
        comp info, with (b) the user's local supporter record."""
        # Local supporter status (from Stripe / payments)
        now_iso = __import__("datetime").datetime.utcnow().isoformat()
        until = user.get("supporter_until")
        is_supporter = bool(until and until > now_iso)

        # Live bridge lookup
        bridge = get_user_status(user["email"])
        comped = bridge.get("network_grant") == "auto"
        exists = bool(bridge.get("exists"))
        renews_at = (
            bridge.get("renews_at")
            or bridge.get("current_period_end")
            or bridge.get("next_billing_date")
            or bridge.get("expires_at")
        )
        return {
            "comped": comped,
            "exists": exists,
            "tier": bridge.get("subscription_tier") if exists else user.get("partner_tier"),
            "renews_at": renews_at if exists else None,
            "property": bridge.get("property") or bridge.get("source"),
            "is_supporter": is_supporter,
            "supporter_until": until,
        }

    return router
