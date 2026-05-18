"""Email-based authentication helpers — password hashing, token issuance.

Sits alongside the existing Emergent Google Auth. Issues the SAME
`session_token` cookie + `user_sessions` row format the rest of the app
already expects, so existing routes don't need changes.
"""
import os
import bcrypt
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Password hashing ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── Single-use tokens (DB-lookup, NOT JWT) ─────────────────────────────
# Used for: email verification, magic-link sign-in, password reset.
TOKEN_KINDS = {"verify", "magic_link", "password_reset"}
TOKEN_TTL_MINUTES = {
    "verify": 60 * 24 * 3,   # 3 days
    "magic_link": 15,        # 15 minutes
    "password_reset": 60,    # 1 hour
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def issue_token(db, *, email: str, kind: str, user_id: Optional[str] = None) -> str:
    """Generate + persist a single-use token. Returns the raw token string."""
    assert kind in TOKEN_KINDS, f"unknown token kind: {kind}"
    token = secrets.token_urlsafe(32)
    expires = _now() + timedelta(minutes=TOKEN_TTL_MINUTES[kind])
    await db.auth_tokens.insert_one({
        "token": token,
        "user_id": user_id,
        "email": (email or "").strip().lower(),
        "kind": kind,
        "expires_at": _iso(expires),
        "used_at": None,
        "created_at": _iso(_now()),
    })
    return token


async def consume_token(db, *, token: str, kind: str) -> Optional[dict]:
    """Look up & mark a token as used. Returns the token doc on success, None
    on missing/expired/already-used/wrong-kind."""
    if not token:
        return None
    doc = await db.auth_tokens.find_one({"token": token}, {"_id": 0})
    if not doc:
        return None
    if doc.get("kind") != kind:
        return None
    if doc.get("used_at"):
        return None
    exp = doc.get("expires_at")
    if exp and exp < _iso(_now()):
        return None
    await db.auth_tokens.update_one(
        {"token": token, "used_at": None},
        {"$set": {"used_at": _iso(_now())}},
    )
    return doc


# ── Brute force protection ─────────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


async def is_locked_out(db, identifier: str) -> bool:
    doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if not doc:
        return False
    locked_until = doc.get("locked_until")
    if not locked_until:
        return False
    return locked_until > _iso(_now())


async def record_failed_attempt(db, identifier: str) -> int:
    """Increment failure count. Returns the new count.
    If we hit MAX_FAILED_ATTEMPTS, lockout for LOCKOUT_MINUTES."""
    doc = await db.login_attempts.find_one_and_update(
        {"identifier": identifier},
        {
            "$inc": {"count": 1},
            "$set": {"last_attempt": _iso(_now())},
            "$setOnInsert": {"identifier": identifier},
        },
        upsert=True,
        return_document=True,
    )
    count = (doc or {}).get("count", 1)
    if count >= MAX_FAILED_ATTEMPTS:
        until = _iso(_now() + timedelta(minutes=LOCKOUT_MINUTES))
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$set": {"locked_until": until}},
        )
    return count


async def clear_attempts(db, identifier: str) -> None:
    await db.login_attempts.delete_one({"identifier": identifier})


# ── Session cookie issuance (reuses existing user_sessions collection) ─
SESSION_TTL_DAYS = 7


async def issue_session(db, *, user_id: str) -> tuple[str, datetime]:
    """Create a session row in user_sessions and return (token, expires_at).
    Caller is responsible for setting the cookie on the response."""
    token = "sess_" + secrets.token_urlsafe(32)
    expires = _now() + timedelta(days=SESSION_TTL_DAYS)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "created_at": _iso(_now()),
        "expires_at": _iso(expires),
    })
    return token, expires


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def app_public_url() -> str:
    return os.environ.get("APP_PUBLIC_URL", "https://thehousingnews.com").rstrip("/")
