"""Brevo (Sendinblue) transactional email + contact list helpers."""
import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "peter@1691inc.com")
SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "Peter Moulton")
API_BASE = "https://api.brevo.com/v3"


def _headers() -> dict:
    return {
        "api-key": BREVO_API_KEY or "",
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    tags: Optional[list[str]] = None,
) -> dict:
    """Send a transactional email. Returns response dict or {'skipped': True}."""
    if not BREVO_API_KEY:
        logger.warning("BREVO_API_KEY missing; skipping email to %s", to_email)
        return {"skipped": True}
    payload = {
        "sender": {"email": SENDER_EMAIL, "name": SENDER_NAME},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "replyTo": {"email": SENDER_EMAIL, "name": SENDER_NAME},
        "subject": subject,
        "htmlContent": html,
        "tags": tags or ["ultradian_network"],
    }
    try:
        r = requests.post(f"{API_BASE}/smtp/email", json=payload, headers=_headers(), timeout=20)
        if r.status_code >= 400:
            logger.error("Brevo send failed %s %s", r.status_code, r.text)
            return {"error": r.text, "status": r.status_code}
        return r.json()
    except Exception as e:
        logger.exception("Brevo exception: %s", e)
        return {"error": str(e)}


def _get_or_create_list(name: str) -> Optional[int]:
    """Find a Brevo contact list by name; create under default folder if missing."""
    if not BREVO_API_KEY:
        return None
    try:
        offset = 0
        while True:
            r = requests.get(
                f"{API_BASE}/contacts/lists",
                params={"limit": 50, "offset": offset},
                headers=_headers(),
                timeout=15,
            )
            if r.status_code >= 400:
                return None
            data = r.json()
            for lst in data.get("lists", []):
                if lst.get("name") == name:
                    return lst.get("id")
            if len(data.get("lists", [])) < 50:
                break
            offset += 50
        # Find a folder
        folders = requests.get(f"{API_BASE}/contacts/folders", params={"limit": 10, "offset": 0}, headers=_headers(), timeout=15)
        folder_id = 1
        if folders.status_code < 400:
            fdata = folders.json().get("folders", [])
            if fdata:
                folder_id = fdata[0].get("id", 1)
        create = requests.post(
            f"{API_BASE}/contacts/lists",
            json={"name": name, "folderId": folder_id},
            headers=_headers(),
            timeout=15,
        )
        if create.status_code < 400:
            return create.json().get("id")
    except Exception as e:
        logger.warning("Brevo list lookup failed: %s", e)
    return None


def add_to_list(email: str, list_name: str, attributes: Optional[dict] = None) -> dict:
    """Upsert a contact in Brevo and add to a named list."""
    if not BREVO_API_KEY:
        return {"skipped": True}
    list_id = _get_or_create_list(list_name)
    payload = {
        "email": email,
        "attributes": attributes or {},
        "listIds": [list_id] if list_id else [],
        "updateEnabled": True,
    }
    try:
        r = requests.post(f"{API_BASE}/contacts", json=payload, headers=_headers(), timeout=15)
        return {"status": r.status_code}
    except Exception as e:
        logger.warning("Brevo contact upsert failed: %s", e)
        return {"error": str(e)}


# ---------- Email templates ----------

def _wrap(body_html: str) -> str:
    return f"""
    <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:32px;">
      <div style="max-width:560px; margin:0 auto; background:#FDFAF4; border:1px solid #E8D4A0; padding:32px;">
        <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.12em; text-transform:uppercase; font-size:12px; margin-bottom:24px;">The Ultradian Network</div>
        {body_html}
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #E8D4A0; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:12px; color:#2C2410;">Pete Moulton</div>
      </div>
    </div>
    """


def send_application_received(email: str, name: str) -> dict:
    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>I got your application to The Ultradian Network. I read every one personally.</p>
      <p>You will hear back from me within 48 hours.</p>
      <p>Pete</p>
    """)
    add_to_list(email, "Network - Applicants", {"FIRSTNAME": name})
    return send_email(email, name, "Your application is in", html, tags=["ultradian_network", "application_received"])


def send_application_accepted(email: str, name: str, app_url: str) -> dict:
    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>You are in. Welcome to the Network.</p>
      <p>Sign in here to finish your profile and write your first post:</p>
      <p><a href="{app_url}" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:12px 24px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600;">Open The Network</a></p>
      <p>Two release windows each day. 8:30am and 5:30pm America/Chicago. That is when the feed updates.</p>
      <p>Pete</p>
    """)
    add_to_list(email, "Network - Members", {"FIRSTNAME": name})
    return send_email(email, name, "You are in", html, tags=["ultradian_network", "application_accepted"])


def send_essay_email(
    to_email: str,
    to_name: str,
    writer_name: str,
    essay_title: str,
    essay_subtitle: str,
    essay_body: str,
    essay_url: str,
) -> dict:
    """Send a per-essay email to one follower. Substack-style."""
    safe_body = (essay_body
                 .replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace("\n\n", "</p><p style=\"font-family:Georgia, serif; font-size:16px; line-height:1.7; color:#2C2410; margin:0 0 16px;\">")
                 .replace("\n", "<br />"))
    subtitle_html = (
        f'<p style="font-family:Georgia, serif; font-size:18px; line-height:1.5; color:#2C2410; font-style:italic; margin:0 0 24px;">{essay_subtitle}</p>'
        if essay_subtitle else ""
    )
    html = _wrap(f"""
      <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:8px;">{writer_name}</div>
      <h1 style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:28px; font-weight:600; color:#2C2410; line-height:1.15; margin:0 0 12px;">{essay_title}</h1>
      {subtitle_html}
      <p style="font-family:Georgia, serif; font-size:16px; line-height:1.7; color:#2C2410; margin:0 0 16px;">{safe_body}</p>
      <p style="margin-top:32px;">
        <a href="{essay_url}" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:10px 20px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px;">Read on the Network</a>
      </p>
    """)
    subject = essay_title or "A new essay"
    return send_email(to_email, to_name, subject, html, tags=["ultradian_network", "essay"])


def send_application_declined(email: str, name: str) -> dict:
    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>Thanks for applying. I am not approving your application right now.</p>
      <p>This is a small, working community. I keep the bar high so the feed stays useful.</p>
      <p>You can apply again in six months. No hard feelings.</p>
      <p>Pete</p>
    """)
    add_to_list(email, "Network - Declined", {"FIRSTNAME": name})
    return send_email(email, name, "About your application", html, tags=["ultradian_network", "application_declined"])


def _digest_item_html(post: dict) -> str:
    """One block per post in the digest."""
    author = post.get("author_name") or "Member"
    market = post.get("author_market") or ""
    market_html = f' <span style="color:#AD893E; font-size:12px;">{market}</span>' if market else ""
    text = (post.get("text") or "")
    if len(text) > 320:
        text = text[:320].rstrip() + "..."
    safe = (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br />"))
    return f"""
    <div style="border-top:1px solid #E8D4A0; padding:20px 0;">
      <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:14px; color:#2C2410;">{author}{market_html}</div>
      <div style="font-family:Georgia, serif; font-size:15px; line-height:1.55; color:#2C2410; margin-top:8px;">{safe}</div>
    </div>
    """


def send_digest_email(email: str, name: str, window_label: str, kind: str, posts: list[dict], picks: list[dict] | None = None) -> dict:
    """Send the AM or PM digest of the just-released batch."""
    count = len(posts)
    if count == 0:
        return {"skipped": True, "reason": "empty"}
    intro_word = "morning" if kind == "am" else "evening"
    items_html = "".join(_digest_item_html(p) for p in posts[:20])
    more_note = ""
    if count > 20:
        more_note = f'<p style="font-family:Georgia, serif; color:#2C2410; font-size:13px; margin-top:16px;">Plus {count - 20} more in the feed.</p>'

    picks_html = ""
    if picks:
        picks_items = "".join(_digest_item_html(p) for p in picks[:3])
        picks_html = f"""
        <div style="margin-top:36px; padding-top:20px; border-top:1px solid #E8D4A0;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:8px;">Pete recommends</div>
          {picks_items}
        </div>
        """

    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>The {intro_word} release just dropped. {count} {'post' if count == 1 else 'posts'} from the room.</p>
      {items_html}
      {more_note}
      {picks_html}
      <p style="margin-top:24px;">
        <a href="{os.environ.get('APP_PUBLIC_URL', '')}/feed" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:10px 20px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px;">Open the feed</a>
      </p>
      <p style="font-family:Georgia, serif; color:#2C2410;">Pete</p>
    """)
    subject = f"The {intro_word} release ({window_label})"
    return send_email(email, name, subject, html, tags=["ultradian_network", f"digest_{kind}"])
