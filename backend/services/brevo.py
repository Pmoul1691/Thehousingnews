"""Transactional email + audience helpers.

Migration note (Feb 2026):
  Brevo permanently suspended our campaigns. This module was rewritten to
  call Resend (https://resend.com) under the hood, but the public function
  signatures (send_email, add_to_list, send_essay_email, send_brief_email,
  send_digest_email, send_application_*) are preserved so the 20+ import
  sites across routes/ and services/ keep working without changes.

  We also keep the old export names BREVO_API_KEY / SENDER_EMAIL / SENDER_NAME
  for backward compatibility with routes/email_health.py — they now resolve
  to the Resend values.

  File name kept as brevo.py to avoid a mass-rename in this same change.
  A follow-up refactor can rename this to services/mailer.py.
"""
import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# ---------- Resend configuration ----------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_API_BASE = "https://api.resend.com"

# Sender defaults. Env vars are read in this order so existing BREVO_*
# overrides keep working on production until the operator migrates them.
SENDER_EMAIL = (
    os.environ.get("RESEND_SENDER_EMAIL")
    or os.environ.get("BREVO_SENDER_EMAIL")
    or "hello@thehousingnews.com"
)
SENDER_NAME = (
    os.environ.get("RESEND_SENDER_NAME")
    or os.environ.get("BREVO_SENDER_NAME")
    or "The Housing News"
)

# Backward-compat alias — routes/email_health.py reads this to flag
# "configured / not configured". Now mirrors RESEND_API_KEY.
BREVO_API_KEY = RESEND_API_KEY

# Default Resend audience to use when add_to_list is called. Created by
# the operator via the Resend dashboard; everyone gets dropped here for
# the v1 cutover. Future refactor can introduce per-list audiences via
# RESEND_AUDIENCE_<LIST>_ID env vars.
RESEND_DEFAULT_AUDIENCE_ID = os.environ.get(
    "RESEND_DEFAULT_AUDIENCE_ID",
    "e680753d-e3c1-40db-9286-1418fc25bf63",  # General audience
)

# Production canonical host. The email-button URL is read from
# APP_PUBLIC_URL but we hard-default to the production host so a missing /
# empty env never silently stamps a relative or empty URL into the email.
PROD_APP_URL = "https://thehousingnews.com"


def app_url() -> str:
    """Return the canonical site URL used to build links inside emails.

    Falls back to the production host when APP_PUBLIC_URL is missing or empty.
    Use this everywhere instead of reading APP_PUBLIC_URL directly so we
    have a single chokepoint to enforce production URLs in outbound mail.
    """
    return (os.environ.get("APP_PUBLIC_URL") or "").rstrip("/") or PROD_APP_URL


def _email_body_has_stale_preview_url(html: str) -> bool:
    """Guardrail: refuse to send anything whose body links back to an
    Emergent preview deployment. A previous incident sent 14k briefs out
    with the old preview host stamped into the 'Open The Daily' button,
    which landed members on the pre-pivot snapshot of the site.
    """
    return "preview.emergentagent.com" in (html or "")


def _resend_headers() -> dict:
    return {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }


def _format_from(email: str, name: str) -> str:
    """Resend wants `Name <email@domain>` as a single string."""
    if name:
        return f"{name} <{email}>"
    return email


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    tags: Optional[list[str]] = None,
    dispatch_id: Optional[str] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> dict:
    """Send a transactional email via Resend. Returns response dict or {'skipped': True}.
    If dispatch_id is given, the HTML is wrapped with a tracking pixel and links are rewritten."""
    if dispatch_id:
        try:
            from services.tracking import wrap_for_tracking
            html = wrap_for_tracking(html, dispatch_id)
        except Exception:
            logger.exception("tracking wrap failed; sending raw")
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY missing; skipping email to %s", to_email)
        return {"skipped": True}
    if _email_body_has_stale_preview_url(html):
        logger.error(
            "BLOCKED outbound email to %s: body contains preview.emergentagent.com "
            "URL. Check APP_PUBLIC_URL on the server — it must be the production "
            "host (e.g. %s), not a preview URL.",
            to_email, PROD_APP_URL,
        )
        return {"error": "blocked: preview URL in email body", "blocked": True}

    from_email = sender_email or SENDER_EMAIL
    from_name = sender_name or SENDER_NAME

    # Resend tag rules: each {name, value} pair must have a unique `name`.
    # Both `name` and `value` must match [a-zA-Z0-9_-] and be <= 256 chars.
    # We turn the incoming string list into uniquely-named tags
    # (`tag_0`, `tag_1`, ...) plus a canonical `category` tag for the
    # first/primary tag so Resend dashboard filtering stays useful.
    raw_tags = list(tags or ["thehousingnews"])
    resend_tags = []
    seen_names = set()
    for i, t in enumerate(raw_tags):
        slug = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in str(t))[:256]
        if not slug:
            continue
        name = "category" if i == 0 else f"tag_{i}"
        if name in seen_names:
            continue
        seen_names.add(name)
        resend_tags.append({"name": name, "value": slug})

    payload = {
        "from": _format_from(from_email, from_name),
        "to": [to_email] if not to_name else [f"{to_name} <{to_email}>"],
        "reply_to": from_email,
        "subject": subject,
        "html": html,
    }
    if resend_tags:
        payload["tags"] = resend_tags

    try:
        r = requests.post(
            f"{RESEND_API_BASE}/emails",
            json=payload,
            headers=_resend_headers(),
            timeout=20,
        )
        if r.status_code >= 400:
            logger.error("Resend send failed %s %s", r.status_code, r.text)
            return {"error": r.text, "status": r.status_code}
        return r.json()
    except Exception as e:
        logger.exception("Resend exception: %s", e)
        return {"error": str(e)}


# ---------- Audiences / contact list helpers ----------

# In the Brevo era we had multiple named lists ("Network - Members",
# "Network - Applicants", "Network - Declined"). Resend models the same
# concept as Audiences. For the v1 cutover we drop every add_to_list
# call into the single default audience so the operator only manages
# one list — finer-grained segmentation can be reintroduced later by
# passing different audience IDs via env vars.


def _audience_id_for_list(list_name: str) -> Optional[str]:
    """Map a legacy Brevo list name to a Resend audience ID. Falls back to
    RESEND_DEFAULT_AUDIENCE_ID if no per-list override is set."""
    if not list_name:
        return RESEND_DEFAULT_AUDIENCE_ID or None
    # Operators can set RESEND_AUDIENCE_NETWORK_MEMBERS_ID, etc.
    slug = (
        list_name.upper()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(",", "")
    )
    env_key = f"RESEND_AUDIENCE_{slug}_ID"
    return os.environ.get(env_key) or RESEND_DEFAULT_AUDIENCE_ID or None


def _get_or_create_list(name: str) -> Optional[str]:
    """Resolve a list name to a Resend audience ID.

    Kept for backward compatibility with the Brevo-era signature. Returns
    a string (UUID) under Resend instead of the old int Brevo list ID.
    """
    if not RESEND_API_KEY:
        return None
    return _audience_id_for_list(name)


def add_to_list(email: str, list_name: str, attributes: Optional[dict] = None) -> dict:
    """Upsert a contact into a Resend audience.

    `attributes` may carry FIRSTNAME / LASTNAME from legacy Brevo callers —
    we map those to Resend's first_name / last_name fields.
    """
    if not RESEND_API_KEY:
        return {"skipped": True}
    audience_id = _audience_id_for_list(list_name)
    if not audience_id:
        return {"skipped": True, "reason": "no audience id"}
    attrs = attributes or {}
    first = (
        attrs.get("FIRSTNAME")
        or attrs.get("FIRST_NAME")
        or attrs.get("first_name")
        or ""
    )
    last = (
        attrs.get("LASTNAME")
        or attrs.get("LAST_NAME")
        or attrs.get("last_name")
        or ""
    )
    payload = {
        "email": email,
        "first_name": first,
        "last_name": last,
        "unsubscribed": False,
    }
    try:
        r = requests.post(
            f"{RESEND_API_BASE}/audiences/{audience_id}/contacts",
            json=payload,
            headers=_resend_headers(),
            timeout=15,
        )
        # Resend returns 200 on create AND on upsert of an existing contact.
        return {"status": r.status_code}
    except Exception as e:
        logger.warning("Resend contact upsert failed: %s", e)
        return {"error": str(e)}


# ---------- Email templates ----------

def _logo_html(size: int = 72) -> str:
    """Render the gold-bloom mark as a centered <img>. Uses the canonical
    production URL so email clients (Gmail/Outlook/Apple Mail) can fetch
    the PNG even when this is sent from a preview deploy where
    APP_PUBLIC_URL would point to a stale preview host.
    """
    return (
        f'<div style="text-align:center; margin:0 0 20px 0;">'
        f'<img src="{PROD_APP_URL}/brand/bloom-gold.png" alt="The Housing News" '
        f'width="{size}" height="{size}" style="display:inline-block; width:{size}px; height:{size}px; max-width:{size}px;" />'
        f'</div>'
    )


def _brief_header_html() -> str:
    """Wordmark banner used at the top of every Morning + Evening Brief.
    Pulls from the production host so the image renders regardless of
    where the brief was rendered (preview, prod, scheduler).
    """
    return (
        f'<div style="text-align:center; margin:0 0 12px 0;">'
        f'<img src="{PROD_APP_URL}/brand/email-header-thn-cream.jpg" '
        f'alt="The Housing News" width="520" '
        f'style="display:block; margin:0 auto; max-width:520px; width:100%; height:auto;" />'
        f'</div>'
    )


def _wrap(body_html: str) -> str:
    return f"""
    <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:32px;">
      <div style="max-width:560px; margin:0 auto; background:#FDFAF4; border:1px solid #E8D4A0; padding:32px;">
        {_logo_html(64)}
        <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.12em; text-transform:uppercase; font-size:12px; margin-bottom:24px; text-align:center;">The Housing News</div>
        {body_html}
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #E8D4A0; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:12px; color:#2C2410;">The Editors</div>
      </div>
    </div>
    """


def send_application_received(email: str, name: str) -> dict:
    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>The editors received your application to The Housing News. Each one is read personally.</p>
      <p>You will hear back from us within 48 hours.</p>
      <p>The Editors</p>
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
      <p>The Editors</p>
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
    dispatch_id: Optional[str] = None,
) -> dict:
    """Send a per-essay email to one follower. Substack-style. Body is rendered from markdown."""
    from services.markdown_render import render as md_render
    body_html = md_render(essay_body) or f"<p>{essay_body}</p>"
    subtitle_html = (
        f'<p style="font-family:Georgia, serif; font-size:18px; line-height:1.5; color:#2C2410; font-style:italic; margin:0 0 24px;">{essay_subtitle}</p>'
        if essay_subtitle else ""
    )
    html = _wrap(f"""
      <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:8px;">{writer_name}</div>
      <h1 style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:28px; font-weight:600; color:#2C2410; line-height:1.15; margin:0 0 12px;">{essay_title}</h1>
      {subtitle_html}
      <div style="font-family:Georgia, serif; font-size:16px; line-height:1.7; color:#2C2410;">{body_html}</div>
      <p style="margin-top:32px;">
        <a href="{essay_url}" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:10px 20px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px;">Read on the Network</a>
      </p>
    """)
    subject = essay_title or "A new essay"
    return send_email(to_email, to_name, subject, html, tags=["ultradian_network", "essay"], dispatch_id=dispatch_id)


def send_application_declined(email: str, name: str) -> dict:
    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>Thanks for applying. We are not approving your application right now.</p>
      <p>This is a small, working community. We keep the bar high so the feed stays useful.</p>
      <p>You can apply again in six months. No hard feelings.</p>
      <p>The Editors</p>
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


def send_digest_email(email: str, name: str, window_label: str, kind: str, posts: list[dict], picks: list[dict] | None = None, dispatch_id: Optional[str] = None, prompt: dict | None = None) -> dict:
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
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:8px;">Staff picks</div>
          {picks_items}
        </div>
        """

    prompt_html = ""
    if prompt and prompt.get("title"):
        prompt_url = f"{app_url()}/prompts/{prompt.get('prompt_id', '')}"
        prompt_body = (prompt.get("body") or "")[:240]
        prompt_html = f"""
        <div style="margin-top:24px; padding:16px 20px; border-left:3px solid #AD893E; background:#FBF6E8;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:6px;">Subject of the week</div>
          <a href="{prompt_url}" style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:16px; color:#2C2410; text-decoration:none;">{prompt['title']}</a>
          {f'<p style="font-family:Georgia, serif; color:#2C2410; font-size:13px; margin:6px 0 0 0;">{prompt_body}</p>' if prompt_body else ''}
        </div>
        """

    html = _wrap(f"""
      <p>Hi {name},</p>
      <p>The {intro_word} release just dropped. {count} {'post' if count == 1 else 'posts'} from the newsroom.</p>
      {prompt_html}
      {items_html}
      {more_note}
      {picks_html}
      <p style="margin-top:24px;">
        <a href="{app_url()}/feed" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:10px 20px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px;">Open the feed</a>
      </p>
      <p style="font-family:Georgia, serif; color:#2C2410;">The Editors</p>
    """)
    subject = f"The {intro_word} release ({window_label})"
    return send_email(email, name, subject, html, tags=["ultradian_network", f"digest_{kind}"], dispatch_id=dispatch_id)


# ---------- Daily Brief (Morning / Evening housing news digest) ----------

BRIEF_SENDER_EMAIL = (
    os.environ.get("RESEND_BRIEF_SENDER_EMAIL")
    or os.environ.get("BRIEF_SENDER_EMAIL")
    or "briefs@thehousingnews.com"
)
BRIEF_SENDER_NAME = (
    os.environ.get("RESEND_BRIEF_SENDER_NAME")
    or os.environ.get("BRIEF_SENDER_NAME")
    or "The Housing News"
)


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _brief_article_row(idx: int, art: dict) -> str:
    pub = art.get("publisher") or {}
    pub_name = _esc(pub.get("name") or "Publisher")
    title = _esc(art.get("title") or "Untitled")
    href = art.get("original_url") or "#"
    snippet = _esc((art.get("snippet") or "")[:180])
    snippet_html = (
        f'<p style="font-family:Georgia, serif; font-size:14px; line-height:1.55; color:#2C2410; margin:6px 0 0 0;">{snippet}</p>'
        if snippet else ""
    )
    return f"""
    <div style="border-top:1px solid #E8D4A0; padding:18px 0;">
      <div style="display:flex; align-items:baseline; gap:10px;">
        <span style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; font-size:13px;">{idx:02d}</span>
        <span style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:10px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; font-weight:600;">{pub_name}</span>
      </div>
      <a href="{href}" style="display:block; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:18px; line-height:1.3; font-weight:600; color:#2C2410; text-decoration:none; margin:6px 0 0 0;">{title}</a>
      {snippet_html}
    </div>
    """


def _brief_podcast_block(pod: dict) -> str:
    ep = pod.get("latest_episode") or {}
    title = _esc(pod.get("title") or "Podcast")
    ep_title = _esc(ep.get("title") or "Latest episode")
    href = ep.get("link") or pod.get("apple_url") or "#"
    return f"""
    <div style="margin-top:28px; padding:18px 20px; border:1px solid #E8D4A0; background:#FBF6E8;">
      <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:10px; letter-spacing:0.22em; text-transform:uppercase; color:#AD893E;">Podcast pick</div>
      <a href="{href}" style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:16px; color:#2C2410; text-decoration:none; display:block; margin-top:6px;">{ep_title}</a>
      <div style="font-family:Georgia, serif; font-style:italic; font-size:13px; color:#2C2410; margin-top:4px;">{title}</div>
    </div>
    """


def _brief_trending_block(topics: list) -> str:
    if not topics:
        return ""
    rows = "".join(
        f'<li style="font-family:Georgia, serif; font-size:14px; color:#2C2410; padding:6px 0; border-bottom:1px solid #E8D4A0;">{_esc(t.get("topic", ""))}'
        f'<span style="float:right; font-family:\'Plus Jakarta Sans\', Arial, sans-serif; font-size:12px; color:#AD893E;">{t.get("count", 0)}</span></li>'
        for t in topics[:5]
    )
    return f"""
    <div style="margin-top:28px;">
      <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:10px; letter-spacing:0.22em; text-transform:uppercase; color:#AD893E; margin-bottom:8px;">Trending across housing · 24h</div>
      <ul style="list-style:none; padding:0; margin:0;">{rows}</ul>
    </div>
    """


def _brief_essay_block(essay: dict, app_url: str) -> str:
    if not essay:
        return ""
    author = (essay.get("author") or {}).get("name") or "A member"
    market = (essay.get("author") or {}).get("market") or ""
    market_html = f' <span style="color:#AD893E;">· {_esc(market)}</span>' if market else ""
    title = _esc(essay.get("title") or "Untitled")
    href = f"{app_url}/essays/{essay.get('post_id', '')}"
    return f"""
    <div style="margin-top:28px; padding-top:20px; border-top:2px solid #2C2410;">
      <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:10px; letter-spacing:0.22em; text-transform:uppercase; color:#AD893E; margin-bottom:8px;">From a member</div>
      <a href="{href}" style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:18px; color:#2C2410; text-decoration:none; line-height:1.3; display:block;">{title}</a>
      <div style="font-family:Georgia, serif; font-style:italic; font-size:13px; color:#2C2410; margin-top:6px;">By {_esc(author)}{market_html}</div>
    </div>
    """


def _brief_wrap(kind: str, body_html: str, app_url: str, unsubscribe_url: str = "", broadcast: bool = False) -> str:
    """Brief-specific shell. Uses cream/gold/ink palette.
    `unsubscribe_url` is passed for non-member newsletter subscribers and
    swaps the footer to a one-click unsubscribe link instead of the
    member-only "manage preferences" link.

    When `broadcast=True`, the footer uses Resend's native unsubscribe merge
    tag `{{{RESEND_UNSUBSCRIBE_URL}}}` — Resend replaces it per-recipient at
    send time. This is what we use for the daily fan-out broadcast to the
    14k+ newsletter audience (no per-row unsubscribe_token needed).
    """
    label = "Morning Brief" if kind == "morning" else "Evening Brief"
    time_str = "7:30 AM CT" if kind == "morning" else "5:30 PM CT"
    today = datetime_now_label()
    if broadcast:
        # Resend swaps this merge tag for a unique per-contact unsub URL.
        footer_html = (
            'You receive these briefs because you subscribed at thehousingnews.com.<br/>'
            '<a href="{{{RESEND_UNSUBSCRIBE_URL}}}" style="color:#AD893E; text-decoration:underline;">Unsubscribe</a>'
        )
    elif unsubscribe_url:
        footer_html = (
            'You receive these briefs because you subscribed at thehousingnews.com.<br/>'
            f'<a href="{unsubscribe_url}" style="color:#AD893E; text-decoration:underline;">Unsubscribe</a>'
        )
    else:
        footer_html = (
            'You receive these briefs because you are a member of The Housing News.<br/>'
            f'<a href="{app_url}/profile" style="color:#AD893E; text-decoration:underline;">Manage your email preferences</a>'
        )
    return f"""
    <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:24px 0;">
      <div style="max-width:600px; margin:0 auto; background:#FDFAF4;">
        <div style="text-align:center; padding-bottom:24px; border-bottom:2px solid #2C2410;">
          {_brief_header_html()}
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#2C2410; font-size:28px; margin-top:16px;">{label}</div>
          <div style="font-family:Georgia, serif; font-style:italic; color:#AD893E; font-size:13px; margin-top:4px;">{today} · {time_str}</div>
        </div>
        <div style="padding:24px 0;">
          {body_html}
        </div>
        <div style="margin-top:32px; padding-top:20px; border-top:1px solid #E8D4A0; text-align:center;">
          <a href="{app_url}/news" style="display:inline-block; background:#2C2410; color:#FDFAF4; padding:12px 28px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px; letter-spacing:0.05em;">Open The Daily →</a>
        </div>
        <div style="margin-top:24px; padding-top:16px; border-top:1px solid #E8D4A0; text-align:center; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:11px; color:#2C2410;">
          {footer_html}
        </div>
      </div>
    </div>
    """


def build_brief_html(kind: str, payload: dict, broadcast: bool = False) -> str:
    """Render the Morning or Evening Brief HTML without sending.

    Used by:
      - `send_brief_email` (transactional, per-recipient)
      - `services.briefings.send_brief_via_broadcast` (Resend Broadcasts)
        which passes `broadcast=True` so the footer uses Resend's native
        `{{{RESEND_UNSUBSCRIBE_URL}}}` merge tag.
    """
    link_base = app_url()
    articles = payload.get("articles") or []
    items_html = "".join(_brief_article_row(i + 1, a) for i, a in enumerate(articles[:8]))
    extras_html = ""
    if kind == "morning" and payload.get("podcast"):
        extras_html += _brief_podcast_block(payload["podcast"])
    if kind == "evening" and payload.get("trending"):
        extras_html += _brief_trending_block(payload["trending"])
    essay_html = _brief_essay_block(payload.get("essay"), link_base)
    body = items_html + extras_html + essay_html
    return _brief_wrap(kind, body, link_base, broadcast=broadcast)


def datetime_now_label() -> str:
    """Returns 'Mon Feb 16'-style label in America/Chicago."""
    try:
        from services.release_window import CHICAGO
        from datetime import datetime as _dt
        now = _dt.now(CHICAGO)
        return now.strftime("%a %b %-d")
    except Exception:
        from datetime import datetime as _dt
        return _dt.utcnow().strftime("%a %b %-d")


def send_brief_email(
    to_email: str,
    to_name: str,
    subject: str,
    kind: str,
    payload: dict,
    dispatch_id: Optional[str] = None,
    unsubscribe_token: Optional[str] = None,
) -> dict:
    """Send a Morning or Evening Brief to one recipient."""
    link_base = app_url()
    articles = payload.get("articles") or []
    items_html = "".join(_brief_article_row(i + 1, a) for i, a in enumerate(articles[:8]))
    extras_html = ""
    if kind == "morning" and payload.get("podcast"):
        extras_html += _brief_podcast_block(payload["podcast"])
    if kind == "evening" and payload.get("trending"):
        extras_html += _brief_trending_block(payload["trending"])
    essay_html = _brief_essay_block(payload.get("essay"), link_base)
    body = items_html + extras_html + essay_html
    unsub_url = f"{link_base}/api/newsletter/unsubscribe?token={unsubscribe_token}" if unsubscribe_token else ""
    html = _brief_wrap(kind, body, link_base, unsubscribe_url=unsub_url)
    return send_email(
        to_email,
        to_name,
        subject,
        html,
        tags=["thehousingnews", f"brief_{kind}"],
        dispatch_id=dispatch_id,
        sender_email=BRIEF_SENDER_EMAIL,
        sender_name=BRIEF_SENDER_NAME,
    )
