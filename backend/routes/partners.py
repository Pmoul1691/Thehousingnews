"""Public endpoint: let prospective members check if their Ultradian Partners /
Ultradia.io email is already comped before they sign in. Rate-limited per IP to
prevent the bridge being used as an email-existence oracle."""
import logging
import re
import time
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException, Query, Request

from services.cross_property import get_user_status

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
    router = APIRouter(prefix="/api/partners", tags=["partners"])

    @router.get("/check")
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
        return {
            "email": email,
            "comped": comped,
            "exists": exists,
            "tier": bridge.get("subscription_tier") if exists else None,
            "name": bridge.get("name") if exists else None,
        }

    return router
