"""Public newsletter subscribe / confirm / unsubscribe flow.

Anyone with an email can subscribe to The Daily Brief — no application,
no membership. Double-opt-in via Brevo:

  1. POST /api/newsletter/subscribe {email}   →  inserts a `pending` row,
                                                  sends confirmation email.
  2. GET  /api/newsletter/confirm?token=...   →  flips row to `confirmed`,
                                                  the brief dispatcher will
                                                  include them from then on.
  3. GET  /api/newsletter/unsubscribe?token=...→ marks `status=unsubscribed`.

Why double-opt-in: protects sender reputation for `briefs@thehousingnews.com`.
A bot can submit a real email; only the human owner of that inbox can click
the confirmation link. Subscribers who don't confirm never receive a brief,
so a typo'd or hostile address never burns deliverability.

Subscribers live in `newsletter_subscribers` (separate from `users` —
they're readers, not members).
"""
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from services.brevo import send_email

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base() -> str:
    return os.environ.get("APP_PUBLIC_URL", "").rstrip("/") or "https://thehousingnews.com"


class SubscribePayload(BaseModel):
    email: EmailStr
    source: Optional[str] = None


def _confirmation_html(email: str, confirm_url: str) -> str:
    return f"""
    <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:32px 0;">
      <div style="max-width:560px; margin:0 auto; background:#FDFAF4; border:1px solid #E8D4A0; padding:36px;">
        <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.22em; text-transform:uppercase; font-size:11px; text-align:center; margin-bottom:24px;">The Housing News</div>
        <h1 style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:26px; line-height:1.25; color:#2C2410; margin:0 0 16px 0; text-align:center;">Confirm your subscription.</h1>
        <p style="font-family:Georgia, serif; font-size:16px; line-height:1.6; color:#2C2410; margin:0 0 24px 0;">
          You signed up to receive <em>The Daily</em> — a twice-daily curated brief on the residential real-estate industry. Click below to confirm and start receiving the morning + evening briefs.
        </p>
        <div style="text-align:center; margin:28px 0;">
          <a href="{confirm_url}" style="display:inline-block; background:#AD893E; color:#FDFAF4; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:14px; padding:14px 28px; border-radius:2px; text-decoration:none;">Confirm subscription &rarr;</a>
        </div>
        <p style="font-family:Georgia, serif; font-size:13px; color:#5C4A1F; line-height:1.55; margin:0;">
          If you didn&apos;t request this, ignore this email — we won&apos;t send anything to {email} unless you click the link.
        </p>
        <p style="font-family:Georgia, serif; font-size:13px; color:#5C4A1F; line-height:1.55; margin:16px 0 0 0;">
          The Daily is free forever for everyone in housing.
        </p>
      </div>
    </div>
    """


def setup(db):
    router = APIRouter(prefix="/api/newsletter", tags=["newsletter"])

    @router.post("/subscribe")
    async def subscribe(payload: SubscribePayload, request: Request):
        email = payload.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email.")

        # If an approved member already has this email, no need to subscribe
        # them again — they already receive the brief by virtue of membership.
        existing_member = await db.users.find_one({"email": email, "status": "approved"})
        if existing_member:
            return {"ok": True, "already_member": True, "message": "You're already on the list as an approved member."}

        existing = await db.newsletter_subscribers.find_one({"email": email})
        if existing and existing.get("status") == "confirmed":
            return {"ok": True, "already_confirmed": True, "message": "You're already subscribed."}
        if existing and existing.get("status") == "unsubscribed":
            # Allow re-subscribe: flip back to pending and resend confirmation.
            confirm_token = secrets.token_urlsafe(24)
            unsub_token = existing.get("unsubscribe_token") or secrets.token_urlsafe(24)
            await db.newsletter_subscribers.update_one(
                {"email": email},
                {"$set": {
                    "status": "pending",
                    "confirm_token": confirm_token,
                    "unsubscribe_token": unsub_token,
                    "resubscribed_at": _now_iso(),
                }},
            )
            row = await db.newsletter_subscribers.find_one({"email": email}, {"_id": 0})
        else:
            confirm_token = secrets.token_urlsafe(24)
            unsub_token = secrets.token_urlsafe(24)
            row = {
                "id": str(uuid.uuid4()),
                "email": email,
                "status": "pending",
                "confirm_token": confirm_token,
                "unsubscribe_token": unsub_token,
                "source": (payload.source or "subscribe")[:80],
                "ip": request.client.host if request.client else None,
                "created_at": _now_iso(),
                "confirmed_at": None,
                "unsubscribed_at": None,
            }
            if existing:
                await db.newsletter_subscribers.update_one({"email": email}, {"$set": row})
            else:
                await db.newsletter_subscribers.insert_one(row)

        confirm_url = f"{_base()}/api/newsletter/confirm?token={confirm_token}"
        html = _confirmation_html(email, confirm_url)
        try:
            send_email(
                to_email=email,
                to_name="",
                subject="Confirm your subscription · The Housing News",
                html=html,
                tags=["thehousingnews", "newsletter_confirmation"],
            )
        except Exception:
            logger.exception("confirmation email failed for %s", email)
            # Still return success — admin can resend manually.
        return {"ok": True, "message": "Check your inbox to confirm your subscription."}

    @router.get("/confirm")
    async def confirm(token: str):
        row = await db.newsletter_subscribers.find_one({"confirm_token": token})
        if not row:
            # Already confirmed? Show a friendly message instead of erroring.
            return _redirect_html("Your link has expired or already been used. If you didn't subscribe, you can ignore this.")
        if row.get("status") == "confirmed":
            return _redirect_html("You're already subscribed. Welcome.")
        await db.newsletter_subscribers.update_one(
            {"email": row["email"]},
            {"$set": {"status": "confirmed", "confirmed_at": _now_iso()},
             "$unset": {"confirm_token": ""}},
        )
        return _redirect_html(
            "You're in.",
            sub=f"You'll receive <em>The Daily</em> at <strong>{row['email']}</strong> twice a day — morning and evening. Free forever.",
        )

    @router.get("/unsubscribe")
    async def unsubscribe(token: str):
        row = await db.newsletter_subscribers.find_one({"unsubscribe_token": token})
        if not row:
            return _redirect_html("Link not found.", sub="If you're still receiving briefs you didn't sign up for, reply to one and we'll remove you by hand.")
        if row.get("status") == "unsubscribed":
            return _redirect_html("You've been unsubscribed.", sub="No further emails will be sent to this address.")
        await db.newsletter_subscribers.update_one(
            {"email": row["email"]},
            {"$set": {"status": "unsubscribed", "unsubscribed_at": _now_iso()}},
        )
        return _redirect_html("You've been unsubscribed.", sub=f"No further briefs will be sent to <strong>{row['email']}</strong>. Change your mind any time — the subscribe page is always open.")

    @router.get("/status")
    async def status():
        """Public stats: how many confirmed subscribers do we have?
        Used by the inline subscribe form for soft social proof."""
        confirmed = await db.newsletter_subscribers.count_documents({"status": "confirmed"})
        approved_members = await db.users.count_documents({"status": "approved", "suspended": {"$ne": True}})
        return {"confirmed_subscribers": confirmed, "approved_members": approved_members, "total_readers": confirmed + approved_members}

    return router


def _redirect_html(headline: str, sub: str = ""):
    """Return a tiny styled HTML page (since these are public links opened
    from email clients, we can't redirect into a React route reliably).
    """
    from fastapi.responses import HTMLResponse
    base = _base()
    html = f"""<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{headline} · The Housing News</title>
  <link rel="icon" href="{base}/brand/favicon-mono.png" />
  <style>
    body {{ font-family: Georgia, serif; background:#FDFAF4; color:#2C2410; margin:0; padding:64px 24px; }}
    .wrap {{ max-width:520px; margin:0 auto; text-align:center; }}
    .eyebrow {{ font-family:'Plus Jakarta Sans', system-ui, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.22em; text-transform:uppercase; font-size:11px; margin-bottom:18px; }}
    h1 {{ font-family:'Plus Jakarta Sans', system-ui, sans-serif; font-weight:600; font-size:36px; line-height:1.15; margin:0 0 16px 0; color:#2C2410; }}
    p {{ font-size:17px; line-height:1.6; color:#2C2410; margin:0 0 24px 0; }}
    .cta {{ display:inline-block; background:#AD893E; color:#FDFAF4; font-family:'Plus Jakarta Sans', system-ui, sans-serif; font-weight:600; font-size:14px; padding:12px 24px; border-radius:2px; text-decoration:none; letter-spacing:0.04em; }}
    .small {{ font-size:13px; color:#5C4A1F; margin-top:32px; }}
  </style>
</head><body>
  <div class="wrap">
    <div class="eyebrow">The Housing News</div>
    <h1>{headline}</h1>
    {f'<p>{sub}</p>' if sub else ''}
    <a class="cta" href="{base}/news">Read The Daily &rarr;</a>
    <div class="small">Free forever for everyone in housing.</div>
  </div>
</body></html>"""
    return HTMLResponse(content=html, status_code=200)
