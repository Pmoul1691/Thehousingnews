"""Email-based auth routes — sit alongside the Emergent Google Auth flow.

Endpoints (all under /api/auth):
  POST /email/signup          — register new email+password account.
  POST /email/signin          — sign in with email+password.
  POST /email/verify/request  — resend verification email.
  POST /email/verify          — consume the verification token from the email.
  POST /magic-link/request    — email a one-time sign-in link.
  POST /magic-link/consume    — exchange a magic-link token for a session.
  POST /password/reset/request
  POST /password/reset/confirm

All successful auth responses set the SAME `session_token` HttpOnly cookie
the Google flow already uses, so the rest of the app doesn't need changes.
"""
import uuid
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, Request, Cookie, Header
from pydantic import BaseModel, EmailStr, Field

from services.auth_helpers import get_current_user
from services.auth_email import (
    hash_password, verify_password,
    issue_token, consume_token,
    is_locked_out, record_failed_attempt, clear_attempts,
    issue_session, set_session_cookie, app_public_url,
)
from services.brevo import send_email

logger = logging.getLogger(__name__)

PASSWORD_MIN = 8


class EmailSignupBody(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)


class EmailSigninBody(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=200)


class EmailOnly(BaseModel):
    email: EmailStr


class TokenOnly(BaseModel):
    token: str = Field(..., min_length=8, max_length=200)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=8, max_length=200)
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=200)


class VerifyRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=200)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "unknown")


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def _user_public(user: dict, has_profile: bool = False) -> dict:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name") or "",
        "picture": user.get("picture", ""),
        "is_admin": bool(user.get("is_admin")),
        "status": user.get("status", "needs_application"),
        "has_profile": has_profile,
        "email_verified": bool(user.get("email_verified")),
        "has_password": bool(user.get("password_hash")),
    }


def setup(db):
    router = APIRouter(prefix="/api/auth", tags=["auth-email"])

    # ── Internal helpers ──────────────────────────────────────────────
    async def _get_or_create_user_for_email(
        email: str,
        *,
        name: Optional[str] = None,
        password_hash: Optional[str] = None,
    ) -> dict:
        """Find user by email; create if missing. Does NOT verify email."""
        email = _norm_email(email)
        u = await db.users.find_one({"email": email}, {"_id": 0})
        if u:
            return u
        # Determine if this email is an admin via env
        from services.auth_helpers import is_admin_email
        is_admin = is_admin_email(email)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        doc = {
            "user_id": user_id,
            "email": email,
            "name": name or email.split("@")[0],
            "picture": "",
            "is_admin": is_admin,
            # "Free forever" pivot: every signup is approved immediately. The
            # legacy "needs_application" gate was retired in Feb 2026.
            "status": "approved",
            "source": "email_signup",
            "email_verified": False,
            "created_at": _now_iso(),
            "last_login_at": _now_iso(),
        }
        if password_hash:
            doc["password_hash"] = password_hash
        await db.users.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def _send_verify_email(email: str, name: str, token: str) -> None:
        link = f"{app_public_url()}/auth/verify-email?token={token}"
        html = f"""
<p>Hi {name or 'there'},</p>
<p>Confirm your email to finish creating your account at The Housing News.</p>
<p><a href="{link}" style="display:inline-block;background:#B89F3D;color:#FDFAF4;text-decoration:none;padding:10px 18px;border-radius:4px;font-family:sans-serif;font-weight:600">Verify my email</a></p>
<p style="font-size:12px;color:#7A6E4F">Or paste this link into your browser:<br>{link}</p>
<p style="font-size:12px;color:#7A6E4F">This link expires in 3 days. If you didn't sign up, you can ignore this email.</p>
"""
        send_email(email, name or email, "Confirm your email — The Housing News", html, tags=["thn_auth", "verify"])

    async def _send_magic_link(email: str, name: str, token: str) -> None:
        link = f"{app_public_url()}/auth/magic?token={token}"
        html = f"""
<p>Hi {name or 'there'},</p>
<p>Click the link below to sign in to The Housing News. It expires in 15 minutes.</p>
<p><a href="{link}" style="display:inline-block;background:#B89F3D;color:#FDFAF4;text-decoration:none;padding:10px 18px;border-radius:4px;font-family:sans-serif;font-weight:600">Sign me in</a></p>
<p style="font-size:12px;color:#7A6E4F">Or paste this link into your browser:<br>{link}</p>
<p style="font-size:12px;color:#7A6E4F">If you didn't request this, you can ignore this email.</p>
"""
        send_email(email, name or email, "Your sign-in link — The Housing News", html, tags=["thn_auth", "magic_link"])

    async def _send_password_reset(email: str, name: str, token: str) -> None:
        link = f"{app_public_url()}/auth/reset-password?token={token}"
        html = f"""
<p>Hi {name or 'there'},</p>
<p>We received a request to reset your password. The link expires in 1 hour.</p>
<p><a href="{link}" style="display:inline-block;background:#B89F3D;color:#FDFAF4;text-decoration:none;padding:10px 18px;border-radius:4px;font-family:sans-serif;font-weight:600">Reset my password</a></p>
<p style="font-size:12px;color:#7A6E4F">Or paste this link into your browser:<br>{link}</p>
<p style="font-size:12px;color:#7A6E4F">If you didn't request this, ignore this email and your password stays the same.</p>
"""
        send_email(email, name or email, "Reset your password — The Housing News", html, tags=["thn_auth", "password_reset"])

    # ── Email + Password ──────────────────────────────────────────────
    @router.post("/email/signup")
    async def email_signup(body: EmailSignupBody, request: Request, response: Response):
        email = _norm_email(body.email)
        # Reject obviously bad emails (EmailStr already validates)
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if existing and existing.get("password_hash"):
            raise HTTPException(status_code=409, detail="An account with this email already exists. Try signing in.")

        pw_hash = hash_password(body.password)
        if existing:
            # Existing user from Google or invite — attach a password to it
            # (account linking). Leave status & email_verified as-is.
            await db.users.update_one(
                {"user_id": existing["user_id"]},
                {"$set": {"password_hash": pw_hash, "last_login_at": _now_iso()}},
            )
            user = existing
            user["password_hash"] = pw_hash
        else:
            user = await _get_or_create_user_for_email(
                email, name=body.name, password_hash=pw_hash,
            )

        # Send verification email (idempotent — they can always resend)
        if not user.get("email_verified"):
            token = await issue_token(db, email=email, kind="verify", user_id=user["user_id"])
            try:
                await _send_verify_email(email, user.get("name") or "", token)
            except Exception:
                logger.exception("verify email send failed for %s", email)

        # Issue a session immediately so the new user is signed in (they can
        # still browse public pages). Posting / joining is gated by
        # email_verified + status checks at the route layer.
        token, _exp = await issue_session(db, user_id=user["user_id"])
        set_session_cookie(response, token)
        has_profile = bool(await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0, "user_id": 1}))
        return {
            **_user_public(user, has_profile),
            "session_token": token,
            "verification_email_sent": not user.get("email_verified"),
        }

    @router.post("/email/signin")
    async def email_signin(body: EmailSigninBody, request: Request, response: Response):
        email = _norm_email(body.email)
        identifier = f"{email}:{_client_ip(request)}"
        if await is_locked_out(db, identifier):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")
        user = await db.users.find_one({"email": email}, {"_id": 0})
        if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
            await record_failed_attempt(db, identifier)
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        await clear_attempts(db, identifier)
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"last_login_at": _now_iso()}},
        )
        token, _exp = await issue_session(db, user_id=user["user_id"])
        set_session_cookie(response, token)
        has_profile = bool(await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0, "user_id": 1}))
        return {**_user_public(user, has_profile), "session_token": token}

    @router.post("/email/verify/request")
    async def email_verify_request(
        body: EmailOnly,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        # If signed in, force their own email; else use the email in the body.
        target_email = _norm_email(body.email)
        user = None
        try:
            user = await get_current_user(db, session_token, authorization)
            target_email = _norm_email(user["email"])
        except HTTPException:
            pass
        u = await db.users.find_one({"email": target_email}, {"_id": 0})
        if not u:
            # Don't reveal whether the account exists.
            return {"ok": True}
        if u.get("email_verified"):
            return {"ok": True, "already_verified": True}
        token = await issue_token(db, email=target_email, kind="verify", user_id=u["user_id"])
        try:
            await _send_verify_email(target_email, u.get("name") or "", token)
        except Exception:
            logger.exception("verify email send failed")
        return {"ok": True}

    @router.post("/email/verify")
    async def email_verify(body: VerifyRequest):
        doc = await consume_token(db, token=body.token, kind="verify")
        if not doc:
            raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
        user = await db.users.find_one({"user_id": doc.get("user_id")}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Account not found.")
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"email_verified": True, "email_verified_at": _now_iso()}},
        )
        return {"ok": True, "user_id": user["user_id"], "email": user["email"]}

    # ── Magic link ────────────────────────────────────────────────────
    @router.post("/magic-link/request")
    async def magic_link_request(body: EmailOnly, request: Request):
        email = _norm_email(body.email)
        # Auto-create a shell account if email is brand new (so the magic
        # link doubles as a passwordless signup).
        u = await db.users.find_one({"email": email}, {"_id": 0})
        if not u:
            u = await _get_or_create_user_for_email(email)
        token = await issue_token(db, email=email, kind="magic_link", user_id=u["user_id"])
        try:
            await _send_magic_link(email, u.get("name") or "", token)
        except Exception:
            logger.exception("magic-link send failed")
        # Generic response so we don't reveal account existence.
        return {"ok": True}

    @router.post("/magic-link/consume")
    async def magic_link_consume(body: TokenOnly, response: Response):
        doc = await consume_token(db, token=body.token, kind="magic_link")
        if not doc:
            raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
        user = await db.users.find_one({"user_id": doc.get("user_id")}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Account not found.")
        # Magic link click implicitly verifies the email (they clicked from inbox).
        if not user.get("email_verified"):
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"email_verified": True, "email_verified_at": _now_iso()}},
            )
            user["email_verified"] = True
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"last_login_at": _now_iso()}},
        )
        token, _exp = await issue_session(db, user_id=user["user_id"])
        set_session_cookie(response, token)
        has_profile = bool(await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0, "user_id": 1}))
        return {**_user_public(user, has_profile), "session_token": token}

    # ── Password reset ────────────────────────────────────────────────
    @router.post("/password/reset/request")
    async def password_reset_request(body: EmailOnly):
        email = _norm_email(body.email)
        u = await db.users.find_one({"email": email}, {"_id": 0})
        # Generic response to avoid email-enumeration.
        if not u or not u.get("password_hash"):
            return {"ok": True}
        token = await issue_token(db, email=email, kind="password_reset", user_id=u["user_id"])
        try:
            await _send_password_reset(email, u.get("name") or "", token)
        except Exception:
            logger.exception("password-reset send failed")
        return {"ok": True}

    @router.post("/password/reset/confirm")
    async def password_reset_confirm(body: PasswordResetConfirm):
        doc = await consume_token(db, token=body.token, kind="password_reset")
        if not doc:
            raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
        user = await db.users.find_one({"user_id": doc.get("user_id")}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Account not found.")
        pw_hash = hash_password(body.password)
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"password_hash": pw_hash, "password_changed_at": _now_iso()}},
        )
        # Invalidate other sessions on password change.
        await db.user_sessions.delete_many({"user_id": user["user_id"]})
        # Clear any remaining brute-force counters for this email (all IPs).
        try:
            await db.login_attempts.delete_many({"identifier": {"$regex": f"^{re.escape(user['email'])}:"}})
        except Exception:
            pass
        return {"ok": True}

    return router
