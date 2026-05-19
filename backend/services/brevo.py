"""Brevo (Sendinblue) transactional email + contact list helpers."""
import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "peter@1691inc.com")
SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "The Housing News")
API_BASE = "https://api.brevo.com/v3"

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
    dispatch_id: Optional[str] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> dict:
    """Send a transactional email. Returns response dict or {'skipped': True}.
    If dispatch_id is given, the HTML is wrapped with a tracking pixel and links are rewritten."""
    if dispatch_id:
        try:
            from services.tracking import wrap_for_tracking
            html = wrap_for_tracking(html, dispatch_id)
        except Exception:
            logger.exception("tracking wrap failed; sending raw")
    if not BREVO_API_KEY:
        logger.warning("BREVO_API_KEY missing; skipping email to %s", to_email)
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
    payload = {
        "sender": {"email": from_email, "name": from_name},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "replyTo": {"email": from_email, "name": from_name},
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

def _logo_html(size: int = 72) -> str:
    """Legacy helper — the gold bloom mark has been removed from all email
    templates. Returns an empty string so existing call sites continue to
    work without rendering anything.
    """
    _ = size
    return ""


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

BRIEF_SENDER_EMAIL = os.environ.get("BRIEF_SENDER_EMAIL", "briefs@thehousingnews.com")
BRIEF_SENDER_NAME = os.environ.get("BRIEF_SENDER_NAME", "The Housing News")


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


def _brief_wrap(kind: str, body_html: str, app_url: str, unsubscribe_url: str = "") -> str:
    """Brief-specific shell. Uses cream/gold/ink palette.
    `unsubscribe_url` is passed for non-member newsletter subscribers and
    swaps the footer to a one-click unsubscribe link instead of the
    member-only "manage preferences" link.
    """
    label = "Morning Brief" if kind == "morning" else "Evening Brief"
    time_str = "7:30 AM CT" if kind == "morning" else "5:30 PM CT"
    today = datetime_now_label()
    if unsubscribe_url:
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
          {_logo_html(72)}
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.28em; text-transform:uppercase; font-size:11px;">The Housing News</div>
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#2C2410; font-size:28px; margin-top:8px;">{label}</div>
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
