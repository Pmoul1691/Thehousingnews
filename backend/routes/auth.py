"""Emergent-managed Google Auth routes."""
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import requests
from fastapi import APIRouter, HTTPException, Response, Cookie, Header, Body
from pydantic import BaseModel

from services.cross_property import get_user_status
from services.brevo import send_application_accepted
from services.auth_helpers import is_admin_email, get_current_user

logger = logging.getLogger(__name__)

SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_TTL_DAYS = 7

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SessionExchange(BaseModel):
    session_id: str


def setup(db):
    """Bind db to the router. Returns the router for inclusion."""

    @router.post("/session")
    async def exchange_session(payload: SessionExchange, response: Response):
        """Exchange Emergent session_id for our session cookie."""
        # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
        try:
            r = requests.get(
                SESSION_DATA_URL,
                headers={"X-Session-ID": payload.session_id},
                timeout=15,
            )
            if r.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session_id")
            data = r.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Emergent session data fetch failed: %s", e)
            raise HTTPException(status_code=502, detail="Auth provider unreachable")

        email = (data.get("email") or "").lower().strip()
        name = data.get("name") or email.split("@")[0]
        picture = data.get("picture") or ""
        session_token = data.get("session_token")
        if not email or not session_token:
            raise HTTPException(status_code=400, detail="Auth payload missing fields")

        # Cross-property bridge call
        bridge = get_user_status(email)
        auto_grant = bridge.get("network_grant") == "auto"
        partner_name = bridge.get("name") if bridge.get("exists") else None

        # Upsert user
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        now_iso = datetime.now(timezone.utc).isoformat()
        if existing:
            user_id = existing["user_id"]
            # Refresh picture/name only if blank
            update = {"last_login_at": now_iso}
            if not existing.get("picture") and picture:
                update["picture"] = picture
            if not existing.get("name") and (partner_name or name):
                update["name"] = partner_name or name
            await db.users.update_one({"user_id": user_id}, {"$set": update})
            user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            admin = is_admin_email(email)
            # Status: admin -> approved, auto_grant -> approved, otherwise -> needs_application
            if admin:
                status = "approved"
            elif auto_grant:
                status = "approved"
            else:
                status = "needs_application"
            user_doc = {
                "user_id": user_id,
                "email": email,
                "name": partner_name or name,
                "picture": picture,
                "is_admin": admin,
                "status": status,  # needs_application | pending | approved | declined
                "source": "partners_auto_grant" if auto_grant else "google",
                "partner_tier": bridge.get("subscription_tier"),
                "created_at": now_iso,
                "last_login_at": now_iso,
            }
            await db.users.insert_one(user_doc)
            user = {k: v for k, v in user_doc.items()}

            # If approved via partners, send accepted email
            if auto_grant and not admin:
                # build app url from request origin via env (best-effort)
                send_application_accepted(email, user["name"], os.environ.get("APP_PUBLIC_URL", ""))

        # Persist our session (mirror Emergent token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
        await db.user_sessions.delete_many({"user_id": user_id, "session_token": session_token})
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "created_at": now_iso,
            "expires_at": expires_at.isoformat(),
        })

        # HttpOnly cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
        )

        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture", ""),
            "is_admin": user.get("is_admin", False),
            "status": user["status"],
            "session_token": session_token,
        }

    @router.get("/me")
    async def get_me(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        # Attach profile if any
        profile = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture", ""),
            "is_admin": user.get("is_admin", False),
            "status": user.get("status", "needs_application"),
            "has_profile": bool(profile),
        }

    @router.post("/logout")
    async def logout(
        response: Response,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        token = session_token
        if not token and authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        if token:
            await db.user_sessions.delete_one({"session_token": token})
        response.delete_cookie("session_token", path="/", samesite="none", secure=True)
        return {"ok": True}

    return router
