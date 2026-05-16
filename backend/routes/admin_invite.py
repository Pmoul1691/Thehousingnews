"""Admin tool: bulk-invite contacts from a named Brevo list.

Workflow (option A from product brief):
  1. Operator hits `GET /api/admin/invite/preview?list=Your+first+list`
     → returns a count + sample of contacts who will be invited (after
     filtering out existing members, blacklisted addresses, and list
     unsubscribers).
  2. Operator hits `POST /api/admin/invite/send` with the same `list` query
     param + a `confirm: "SEND"` body to actually pre-seed user rows and
     dispatch the invite email through Brevo.

Pre-seed semantics: each new contact gets a `users` row with
`status="invited"` + the original Brevo first/last name + an invite_token.
When they sign in with Google, auth.py promotes them to `status="approved"`
automatically (see auth.py for the matching logic).

Idempotency: re-running `send` is safe — contacts who already have a `users`
row are skipped. So the operator can paginate this in chunks or retry on
network failure without sending duplicate emails.
"""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email
from services.brevo import send_email
from services.brevo_contacts import (
    find_list_by_name,
    iter_list_contacts,
    normalize_contact,
)

logger = logging.getLogger(__name__)

DEFAULT_LIST_NAME = os.environ.get("BREVO_INVITE_LIST_NAME", "Your first list")
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "https://thehousingnews.com")

INVITE_SUBJECT = "Your spot on The Housing News is ready"

# Cache the preview result for 5 minutes — the underlying data is a Brevo
# list that changes slowly, and the full scan is a 30+ second operation
# for lists with 10k+ contacts. We invalidate on /send anyway.
_PREVIEW_CACHE: dict = {}
_PREVIEW_TTL_S = 300


def _invite_html(first_name: str, claim_url: str) -> str:
    """Plain, editorial-looking invite. Brevo will track opens/clicks via the
    `tracking` wrapper applied by send_email when a dispatch_id is provided —
    we don't pass one here because this is a one-off bulk send, not a
    repeating newsletter dispatch."""
    greeting = f"{first_name}," if first_name else "Friend,"
    return f"""\
<!doctype html>
<html><body style="font-family:Georgia,'Times New Roman',serif;color:#2C2410;background:#FDFAF4;padding:32px 0;margin:0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#FDFAF4;">
        <tr><td style="padding:16px 28px 32px;">
          <p style="font-family:'Plus Jakarta Sans',Helvetica,sans-serif;font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:#B89048;font-weight:600;margin:0 0 24px;">
            The Housing News
          </p>
          <p style="font-size:18px;line-height:1.7;margin:0 0 18px;">{greeting}</p>
          <p style="font-size:17px;line-height:1.7;margin:0 0 18px;">
            We've held a spot for you in <em>The Housing News</em> &mdash; a daily magazine for the real estate industry.
          </p>
          <p style="font-size:17px;line-height:1.7;margin:0 0 28px;">
            Click the button below to claim your membership. You'll sign in with Google (use the same email this note came to) and skip the application form &mdash; we already know who you are.
          </p>
          <p style="margin:0 0 28px;">
            <a href="{claim_url}" style="background:#B89048;color:#FDFAF4;font-family:'Plus Jakarta Sans',Helvetica,sans-serif;font-weight:600;font-size:14px;text-decoration:none;padding:12px 28px;border-radius:999px;display:inline-block;">
              Claim your spot
            </a>
          </p>
          <p style="font-size:14px;line-height:1.7;color:#7a6a44;font-style:italic;margin:0 0 12px;">
            Released twice a day, at 8:30am and 5:30pm Chicago time. Written by people who close deals.
          </p>
          <p style="font-size:12px;line-height:1.7;color:#7a6a44;margin:32px 0 0;border-top:1px solid #E8D4A0;padding-top:16px;">
            If this isn't for you, just ignore this email and we won't bother you again.<br/>
            <a href="{claim_url}" style="color:#B89048;">{claim_url}</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


class SendPayload(BaseModel):
    confirm: str = Field(..., description='Must be the literal string "SEND".')
    list_name: Optional[str] = Field(default=None, max_length=200)
    limit: int = Field(default=500, ge=1, le=5000)
    dry_run: bool = Field(default=False)


def setup(db):
    router = APIRouter(prefix="/api/admin/invite", tags=["admin-invite"])

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    async def _build_preview(list_name: str, use_cache: bool = True) -> dict:
        import time as _time
        cache_key = list_name.strip().lower()
        if use_cache:
            cached = _PREVIEW_CACHE.get(cache_key)
            if cached and cached[1] > _time.time():
                return cached[0]

        lst = find_list_by_name(list_name)
        if not lst:
            raise HTTPException(status_code=404, detail=f'Brevo list "{list_name}" not found')
        list_id = lst.get("id")

        existing_emails = set()
        async for u in db.users.find({}, {"_id": 0, "email": 1}):
            if u.get("email"):
                existing_emails.add(u["email"].lower())

        candidates = []
        skipped_existing = 0
        skipped_blacklisted = 0
        skipped_unsub = 0
        total = 0
        for raw in iter_list_contacts(list_id):
            total += 1
            c = normalize_contact(raw)
            if not c["email"]:
                continue
            if c["blacklisted"]:
                skipped_blacklisted += 1
                continue
            if c["list_unsubscribed"]:
                skipped_unsub += 1
                continue
            if c["email"] in existing_emails:
                skipped_existing += 1
                continue
            candidates.append(c)

        result = {
            "list": {"id": list_id, "name": lst.get("name"), "subscribers": lst.get("totalSubscribers")},
            "totals": {
                "contacts_in_list": total,
                "will_invite": len(candidates),
                "skipped_already_member": skipped_existing,
                "skipped_blacklisted": skipped_blacklisted,
                "skipped_unsubscribed": skipped_unsub,
            },
            "candidates": candidates,
        }
        _PREVIEW_CACHE[cache_key] = (result, _time.time() + _PREVIEW_TTL_S)
        return result

    @router.get("/preview")
    async def preview(
        list_name: str = Query(default=DEFAULT_LIST_NAME, alias="list"),
        admin=Depends(_admin),
    ):
        """Dry-run: who would receive an invite from this Brevo list."""
        result = await _build_preview(list_name)
        # Trim the response for the UI — frontend only needs first 50 names.
        return {
            **result,
            "candidates": result["candidates"][:50],
            "sample_only": len(result["candidates"]) > 50,
        }

    @router.get("/lists")
    async def lists(admin=Depends(_admin)):
        """Optional: surface every Brevo list so the operator can pick one."""
        from services.brevo_contacts import list_brevo_lists
        return {"lists": list_brevo_lists()}

    @router.post("/send")
    async def send(payload: SendPayload, admin=Depends(_admin)):
        """Send the invite emails. `confirm` must be the literal string SEND."""
        if (payload.confirm or "").strip() != "SEND":
            raise HTTPException(status_code=400, detail='Confirmation token must be the literal string "SEND".')

        list_name = (payload.list_name or DEFAULT_LIST_NAME).strip()
        # Send must always go off a fresh scan — no cached results.
        preview_data = await _build_preview(list_name, use_cache=False)
        # Bust the cache so future preview calls reflect the new pre-seeds.
        _PREVIEW_CACHE.pop(list_name.lower(), None)
        all_candidates = preview_data["candidates"][: payload.limit]

        sent = 0
        failed = 0
        skipped_race = 0  # someone signed up between preview and send
        now_iso = datetime.now(timezone.utc).isoformat()

        for c in all_candidates:
            email = c["email"]
            # Race: ensure the user wasn't created since preview built.
            already = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
            if already:
                skipped_race += 1
                continue

            invite_token = secrets.token_urlsafe(24)
            user_id = f"user_inv_{secrets.token_hex(6)}"
            user_doc = {
                "user_id": user_id,
                "email": email,
                "name": c["name"] or email.split("@")[0],
                "first_name": c["first_name"] or None,
                "last_name": c["last_name"] or None,
                "picture": "",
                "is_admin": False,
                "status": "invited",
                "source": "brevo_invite",
                "invite_token": invite_token,
                "invite_list_name": list_name,
                "invited_at": now_iso,
                "invited_by_admin_email": admin["email"],
                "created_at": now_iso,
                "last_login_at": None,
            }
            if payload.dry_run:
                sent += 1
                continue

            # Insert pre-seed user row first, send email second. If the email
            # send fails, the user can still claim on next visit — we just
            # won't have notified them yet.
            try:
                await db.users.insert_one(user_doc)
            except Exception as e:
                logger.warning("Failed to pre-seed user %s: %s", email, e)
                failed += 1
                continue

            claim_url = f"{APP_PUBLIC_URL.rstrip('/')}/claim?token={invite_token}"
            html = _invite_html(c["first_name"], claim_url)
            resp = send_email(
                to_email=email,
                to_name=c["name"] or "",
                subject=INVITE_SUBJECT,
                html=html,
                tags=["thn_brevo_invite_bulk"],
            )
            if resp.get("error") or resp.get("skipped"):
                failed += 1
                # Mark so an operator can re-send later by scanning failures.
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"invite_email_status": "failed", "invite_email_error": str(resp)[:300]}},
                )
            else:
                sent += 1
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"invite_email_status": "sent", "invite_email_message_id": resp.get("messageId")}},
                )

        return {
            "ok": True,
            "list": preview_data["list"],
            "dry_run": payload.dry_run,
            "sent": sent,
            "failed": failed,
            "skipped_already_member_race": skipped_race,
        }

    return router
