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

        # Upsert user. Defensive: if no user record exists for this email but a
        # stale profile does (e.g. previous user row was deleted out of band by
        # test cleanup or a database migration), reuse the profile's user_id so
        # the member is stitched back to their existing profile instead of
        # being sent through onboarding again.
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        now_iso = datetime.now(timezone.utc).isoformat()
        if existing:
            user_id = existing["user_id"]
            # Refresh picture/name only if blank
            update = {"last_login_at": now_iso}
            # Google sign-in implicitly verifies the email (Google did the work).
            if not existing.get("email_verified"):
                update["email_verified"] = True
                update["email_verified_at"] = now_iso
            if not existing.get("picture") and picture:
                update["picture"] = picture
            if not existing.get("name") and (partner_name or name):
                update["name"] = partner_name or name
            # Brevo bulk-invited users were pre-seeded with status="invited".
            # The moment they sign in with Google (proving they own the inbox
            # the invite was sent to) we auto-promote them to approved so they
            # skip the application form.
            was_invited = existing.get("status") == "invited"
            if was_invited:
                update["status"] = "approved"
                update["invited_claimed_at"] = now_iso
                update["source"] = existing.get("source") or "brevo_invite"
                logger.info("Brevo invite claimed by %s", email)
            await db.users.update_one({"user_id": user_id}, {"$set": update})
            user = await db.users.find_one({"user_id": user_id}, {"_id": 0})

            # Stub-profile bootstrap: a freshly-promoted invitee shouldn't be
            # walled at /onboarding; we want them straight in the feed with
            # a welcome banner. Drop a minimal profile row so `has_profile`
            # is true. The /feed page detects "stub" (empty market+objectives)
            # and surfaces a "Finish setup" prompt without blocking reads.
            if was_invited and not await db.profiles.find_one(
                {"user_id": user_id}, {"_id": 0, "user_id": 1}
            ):
                first_name = existing.get("first_name") or (user.get("name") or "").split(" ")[0]
                last_name = existing.get("last_name") or ""
                display_name = (
                    f"{first_name} {last_name}".strip()
                    or user.get("name")
                    or email.split("@")[0]
                )
                await db.profiles.insert_one({
                    "user_id": user_id,
                    "email": email,
                    "name": display_name,
                    "market": "",
                    "bio": "",
                    "avatar_path": None,
                    "objectives": [],
                    "objectives_version": 0,
                    "linkedin_url": None,
                    "is_stub": True,
                    "stub_source": "brevo_invite",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                })
                logger.info("Stub profile created for invitee %s", email)
        else:
            existing_profile = await db.profiles.find_one({"email": email}, {"_id": 0})
            user_id = existing_profile["user_id"] if existing_profile else f"user_{uuid.uuid4().hex[:12]}"
            admin = is_admin_email(email)
            # "Free forever" pivot: every new signup is approved on the spot.
            # Membership status is no longer a gate. Admin / partner / recovered
            # accounts remain approved for the same reasons they were before.
            status = "approved"
            _ = (admin, auto_grant, existing_profile)  # retained for source attribution below
            user_doc = {
                "user_id": user_id,
                "email": email,
                "name": partner_name or name,
                "picture": picture,
                "is_admin": admin,
                "status": status,  # needs_application | pending | approved | declined
                "source": (
                    "partners_auto_grant" if auto_grant
                    else ("profile_recovery" if existing_profile else "google")
                ),
                "partner_tier": bridge.get("subscription_tier"),
                "email_verified": True,  # Google sign-in verifies the email
                "email_verified_at": now_iso,
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

        # Compute has_profile so the frontend can skip the follow-up /auth/me round trip.
        has_profile = bool(await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0, "user_id": 1}))

        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture", ""),
            "is_admin": user.get("is_admin", False),
            "status": user["status"],
            "has_profile": has_profile,
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
        prof = profile or {}
        # "profile_complete" = at least a real name and a market on a
        # non-stub profile. Mirrors the directory definition so a member
        # who flips the banner CTA lands them in the right state.
        profile_complete = bool(
            (prof.get("name") or "").strip()
            and (prof.get("market") or "").strip()
            and not prof.get("is_stub")
        )
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture", ""),
            "is_admin": user.get("is_admin", False),
            "status": user.get("status", "needs_application"),
            "has_profile": bool(profile),
            "profile_complete": profile_complete,
            "email_verified": bool(user.get("email_verified")),
            "has_password": bool(user.get("password_hash")),
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

    @router.get("/invite/lookup")
    async def invite_lookup(token: str):
        """Public endpoint hit by the /claim page so it can greet the
        invitee by name and confirm which inbox the invite was sent to.

        Returns a tiny shape — no sensitive data, no claim side-effects.
        The actual promotion to status="approved" happens server-side the
        moment they sign in with Google using the matching email."""
        if not token or len(token) > 200:
            raise HTTPException(status_code=400, detail="Bad token")
        invitee = await db.users.find_one(
            {"invite_token": token, "status": "invited"},
            {"_id": 0, "email": 1, "first_name": 1, "name": 1},
        )
        if not invitee:
            raise HTTPException(status_code=404, detail="Invite not found or already claimed")
        return {
            "email": invitee["email"],
            "first_name": invitee.get("first_name") or (invitee.get("name") or "").split(" ")[0],
            "name": invitee.get("name"),
        }

    return router
