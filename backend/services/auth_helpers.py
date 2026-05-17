"""Authentication helpers shared across routes."""
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import Cookie, Header, HTTPException


ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


def is_admin_email(email: str) -> bool:
    return (email or "").lower() in ADMIN_EMAILS


async def get_current_user(
    db,
    session_token: Optional[str] = None,
    authorization: Optional[str] = None,
):
    """Resolve the current user from cookie session_token, Bearer header, or
    a Personal Access Token (PAT) Bearer token (prefix `thn_pat_`).

    db: motor async db
    """
    token = session_token
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # PAT path — used by automation (e.g. an LLM agent posting on a user's behalf).
    if token.startswith("thn_pat_"):
        from services.pat_service import resolve_pat
        user = await resolve_pat(db, token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        return user

    # Legacy session-token path.
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = sess.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User missing")
    return user


def auth_dep(db):
    """Factory: returns a FastAPI dependency bound to the given db."""

    async def _dep(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    return _dep


def admin_dep(db):
    user_dep = auth_dep(db)

    async def _dep(user=None, session_token: Optional[str] = Cookie(default=None), authorization: Optional[str] = Header(default=None)):
        user = await user_dep(session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    return _dep
