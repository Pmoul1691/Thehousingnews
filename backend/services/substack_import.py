"""Daily Substack RSS importer. Pulls Pete's essays from his Substack feed and
publishes them as approved essays attributed to the first matching admin user.

De-branded: no Substack attribution surfaced in the UI. We strip the trailing
hashtag cluster Substack/LinkedIn syndication adds because it does not fit the
calm-by-design voice of the Network.
"""
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import feedparser
from markdownify import markdownify

from services.release_window import next_window
from services.substack_fetch import fetch_substack_media

logger = logging.getLogger(__name__)

ADMIN_FALLBACK_EMAILS = ("peter@1691inc.com", "peter@ultradianpartners.com")
PREVIEW_AUTHORS = ("peter moulton", "pete moulton")


def _strip_trailing_hashtag_block(text: str) -> str:
    """Substack/LinkedIn posts often end with a flurry of #Hashtags. Drop them."""
    if not text:
        return text
    lines = text.rstrip().splitlines()
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        tokens = last.split()
        if tokens and all(t.startswith("#") and len(t) > 1 for t in tokens):
            lines.pop()
            continue
        # Strip an inline trailing run of hashtags on the final line
        stripped_inline = re.sub(r"(\s+#[A-Za-z0-9_]+){2,}\s*$", "", last).rstrip()
        if stripped_inline != last:
            lines[-1] = stripped_inline
        break
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def _parse_published(entry) -> str:
    pp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if pp:
        try:
            return datetime(*pp[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _entry_content_html(entry) -> str:
    """Prefer full content over summary."""
    if hasattr(entry, "content") and entry.content:
        for c in entry.content:
            if c.get("value"):
                return c["value"]
    return getattr(entry, "summary", "") or getattr(entry, "description", "") or ""


def _to_markdown(html: str) -> str:
    md = markdownify(html, heading_style="ATX", strip=["script", "style"])
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return _strip_trailing_hashtag_block(md)


def _first_image_src(html: str) -> Optional[str]:
    if not html:
        return None
    m = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", html, re.IGNORECASE)
    return m.group(1) if m else None


async def _pick_admin_user(db) -> Optional[dict]:
    for email in ADMIN_FALLBACK_EMAILS:
        u = await db.users.find_one({"email": email}, {"_id": 0})
        if u:
            return u
    return await db.users.find_one({"is_admin": True, "status": "approved"}, {"_id": 0})


async def import_substack_feed(db, feed_url: Optional[str] = None) -> dict:
    """Fetch the configured Substack RSS, insert any new entries as essays.

    Returns a summary dict with counts.
    """
    url = feed_url or os.environ.get("SUBSTACK_RSS_URL", "").strip()
    if not url:
        logger.info("SUBSTACK_RSS_URL not set; skipping import")
        return {"ok": False, "reason": "no_feed_url", "imported": 0, "skipped": 0}

    admin = await _pick_admin_user(db)
    if not admin:
        logger.warning("No admin user available to attribute imported essays")
        return {"ok": False, "reason": "no_admin_user", "imported": 0, "skipped": 0}

    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        logger.warning("Feed parse error: %s", getattr(parsed, "bozo_exception", "unknown"))
        return {"ok": False, "reason": "feed_parse_error", "imported": 0, "skipped": 0}

    imported = []
    skipped = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    # New Substack imports release at the next batched window so they join the
    # Network's calm-by-design rhythm instead of appearing immediately.
    release_iso = next_window().astimezone(timezone.utc).isoformat()

    for entry in parsed.entries:
        source_guid = getattr(entry, "id", None) or getattr(entry, "link", None)
        source_url = getattr(entry, "link", None) or source_guid
        if not source_guid:
            skipped += 1
            continue

        existing = await db.posts.find_one(
            {"$or": [{"source_guid": source_guid}, {"source_url": source_url}]},
            {"_id": 0, "post_id": 1},
        )
        if existing:
            skipped += 1
            continue

        title = (getattr(entry, "title", "") or "").strip()
        if not title:
            skipped += 1
            continue

        html = _entry_content_html(entry)
        text_md = _to_markdown(html)
        if not text_md:
            skipped += 1
            continue

        subtitle = getattr(entry, "subtitle", None)
        if subtitle:
            subtitle = subtitle.strip() or None

        # Original Substack publish date - preserved on the record for the
        # "Originally published on Substack, {date}" footnote. The platform's
        # `release_at` is gated to the next batched release window so the
        # essay does not jump the calm-by-design rhythm.
        source_published_iso = _parse_published(entry)

        # Substack videos (Mux HLS) are intentionally NOT imported — they
        # don't play interactively in our reader and the user prefers the
        # essay text to stand on its own. Re-enable by uncommenting and
        # restoring the `fetch_substack_media` call below.
        media: list = []
        # try:
        #     mux = fetch_substack_media(source_url) if source_url else None
        #     if mux:
        #         media.append(mux)
        # except Exception as _e:
        #     logger.warning("Mux fetch failed for %s: %s", source_url, _e)

        post_id = f"post_{uuid.uuid4().hex[:12]}"
        doc = {
            "post_id": post_id,
            "user_id": admin["user_id"],
            "kind": "essay",
            "title": title,
            "subtitle": subtitle,
            "text": text_md,
            "image_path": None,
            "media": media,
            "status": "approved",
            "release_at": release_iso,
            "created_at": now_iso,
            "source": "substack_import",
            "source_guid": source_guid,
            "source_url": source_url,
            "source_published_at": source_published_iso,
            "imported_at": now_iso,
        }
        external_image = _first_image_src(html)
        if external_image:
            doc["source_image_url"] = external_image
        try:
            await db.posts.insert_one(doc)
            imported.append({"post_id": post_id, "title": title, "source_url": source_url})
        except Exception as e:
            logger.exception("Insert failed for %s: %s", source_guid, e)
            skipped += 1

    logger.info("Substack import: %s imported, %s skipped", len(imported), skipped)
    return {
        "ok": True,
        "feed_url": url,
        "imported": len(imported),
        "skipped": skipped,
        "items": imported,
    }
