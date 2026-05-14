"""RSS ingestion for the public aggregator.

Hard rules enforced here (NOT in CSS):
- Snippet is capped at 280 characters OR end of 2nd sentence, whichever is shorter.
- If display_mode == "headline_only" we store an empty snippet.
- Image URLs are stored as-is from the feed; we never download, rehost, or proxy.
- Each headline links to the original publisher URL — there is no internal article view.
- Items older than 90 days hide from public lists; older than 120 days are deleted.

Respects each publisher's robots.txt with a descriptive User-Agent. Failures in one
publisher never cascade into others.
"""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "thehousingnews-aggregator/1.0 (+https://thehousingnews.com/about)"
SNIPPET_MAX_CHARS = 280
ITEM_TTL_DAYS = 90
ITEM_HARD_DELETE_DAYS = 120
FETCH_TIMEOUT_SECONDS = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    try:
        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def _truncate_snippet(text: str, max_chars: int = SNIPPET_MAX_CHARS) -> str:
    """Cap snippet at 2 sentences OR max_chars, whichever is shorter. Server-side."""
    if not text:
        return ""
    # Find first two sentence boundaries: . ! ?  (followed by space or end)
    sentences = re.findall(r"[^.!?]+[.!?]", text, flags=re.S)
    if len(sentences) >= 2:
        two_sentences = "".join(sentences[:2]).strip()
    else:
        two_sentences = text.strip()
    if len(two_sentences) <= max_chars:
        return two_sentences
    cut = two_sentences[:max_chars].rstrip()
    # Try to back off to last space to avoid mid-word truncation
    last_space = cut.rfind(" ")
    if last_space > 60:
        cut = cut[:last_space]
    return cut.rstrip() + "..."


def _extract_thumbnail(entry) -> Optional[str]:
    """Look for an image URL in this order: media:thumbnail, media:content,
    enclosure with image MIME, first <img> in summary HTML. Return URL only."""
    # media_thumbnail
    media_thumb = entry.get("media_thumbnail") or []
    if isinstance(media_thumb, list) and media_thumb:
        url = (media_thumb[0] or {}).get("url")
        if url:
            return url
    # media_content
    media_content = entry.get("media_content") or []
    if isinstance(media_content, list):
        for mc in media_content:
            url = mc.get("url") if isinstance(mc, dict) else None
            mtype = (mc.get("medium") or mc.get("type") or "") if isinstance(mc, dict) else ""
            if url and ("image" in mtype.lower() or not mtype):
                return url
    # enclosures
    enclosures = entry.get("enclosures") or []
    for enc in enclosures:
        url = (enc or {}).get("href") or (enc or {}).get("url")
        mtype = ((enc or {}).get("type") or "").lower()
        if url and mtype.startswith("image"):
            return url
    # First <img> in summary
    summary = entry.get("summary") or ""
    if summary:
        try:
            soup = BeautifulSoup(summary, "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                return img["src"]
        except Exception:
            pass
    return None


def _published_at(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        v = entry.get(key)
        if v:
            try:
                return datetime(*v[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return _now()


def _robots_allows(feed_url: str) -> bool:
    """Best-effort robots.txt check. Failures default to allow (we'll still
    honor any 403 from the actual feed fetch)."""
    try:
        parsed = urlparse(feed_url)
        robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            r = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=8)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                return True
        except Exception:
            return True
        return rp.can_fetch(USER_AGENT, feed_url)
    except Exception:
        return True


def fetch_feed_xml(feed_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (xml_text, error_str). error_str is None on success."""
    try:
        r = requests.get(
            feed_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
            timeout=FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None, f"http_{r.status_code}"
        return r.text, None
    except requests.Timeout:
        return None, "timeout"
    except Exception as e:
        return None, f"fetch_error:{type(e).__name__}"


def parse_entries(xml_text: str, publisher: dict) -> list[dict]:
    """Parse RSS/Atom XML into normalized article dicts ready for Mongo upsert."""
    parsed = feedparser.parse(xml_text)
    out: list[dict] = []
    display_mode = publisher.get("display_mode") or "headline_and_snippet"
    for entry in parsed.entries or []:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        guid = entry.get("id") or entry.get("guid") or link
        # Snippet
        if display_mode == "headline_only":
            snippet = ""
        else:
            raw = entry.get("content_snippet") or entry.get("summary") or entry.get("description") or ""
            snippet = _truncate_snippet(_strip_html(raw))
        thumb = _extract_thumbnail(entry)
        pub_at = _published_at(entry)
        out.append({
            "guid": str(guid),
            "title": title[:500],
            "snippet": snippet,
            "thumbnail_url": thumb,
            "original_url": link,
            "published_at": pub_at.isoformat(),
        })
    return out


async def ingest_publisher(db, publisher: dict) -> dict:
    """Fetch + parse a single publisher. Updates Mongo and returns a tiny stats
    dict. Wrapped by callers in try/except so one bad feed never affects others."""
    pub_id = publisher["id"]
    feed_url = publisher["feed_url"]

    # robots.txt
    if not _robots_allows(feed_url):
        await db.agg_publishers.update_one(
            {"id": pub_id},
            {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": "robots_disallowed"}},
        )
        return {"publisher_id": pub_id, "ok": False, "reason": "robots_disallowed", "inserted": 0}

    xml, err = fetch_feed_xml(feed_url)
    if err:
        await db.agg_publishers.update_one(
            {"id": pub_id},
            {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": err}},
        )
        return {"publisher_id": pub_id, "ok": False, "reason": err, "inserted": 0}

    try:
        entries = parse_entries(xml, publisher)
    except Exception as e:
        logger.exception("parse failure for %s: %s", pub_id, e)
        await db.agg_publishers.update_one(
            {"id": pub_id},
            {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": f"parse_error:{type(e).__name__}"}},
        )
        return {"publisher_id": pub_id, "ok": False, "reason": "parse_error", "inserted": 0}

    inserted = 0
    skipped = 0
    fetched_at = _now_iso()
    for art in entries:
        published_at = datetime.fromisoformat(art["published_at"])
        expires_at = published_at + timedelta(days=ITEM_TTL_DAYS)
        # Dedupe key: (publisher_id, guid). Fall back to original_url if guid is missing.
        guid = art["guid"] or art["original_url"]
        doc = {
            "id": str(uuid.uuid4()),
            "publisher_id": pub_id,
            "guid": guid,
            "title": art["title"],
            "snippet": art["snippet"],
            "thumbnail_url": art["thumbnail_url"],
            "original_url": art["original_url"],
            "published_at": art["published_at"],
            "fetched_at": fetched_at,
            "expires_at": expires_at.isoformat(),
            "hidden": False,
            "created_at": _now_iso(),
        }
        # Try insert; if duplicate (publisher_id, guid), skip
        try:
            res = await db.agg_articles.update_one(
                {"publisher_id": pub_id, "guid": guid},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning("article upsert failed (pub=%s guid=%s): %s", pub_id, guid, e)

    await db.agg_publishers.update_one(
        {"id": pub_id},
        {"$set": {"last_fetched_at": fetched_at, "last_fetch_status": "ok"}},
    )
    return {"publisher_id": pub_id, "ok": True, "inserted": inserted, "skipped": skipped, "parsed": len(entries)}


async def ingest_all_active(db) -> dict:
    """Iterate every active publisher whose refresh window has elapsed. Each
    publisher runs in isolation — exceptions are caught and reported."""
    now = _now()
    cur = db.agg_publishers.find({"active": True}, {"_id": 0})
    publishers = await cur.to_list(500)
    results = []
    for p in publishers:
        # Refresh window check
        last = p.get("last_fetched_at")
        refresh_minutes = int(p.get("refresh_minutes") or 30)
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if (now - last_dt) < timedelta(minutes=refresh_minutes):
                    continue
            except Exception:
                pass
        try:
            r = await ingest_publisher(db, p)
        except Exception as e:
            logger.exception("ingest crashed for %s: %s", p.get("id"), e)
            r = {"publisher_id": p.get("id"), "ok": False, "reason": "crash"}
            try:
                await db.agg_publishers.update_one(
                    {"id": p["id"]},
                    {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": f"crash:{type(e).__name__}"}},
                )
            except Exception:
                pass
        results.append(r)
    return {"ran": len(results), "results": results}


async def prune_expired(db) -> dict:
    """Hide items past 90d; hard-delete items past 120d."""
    now = _now()
    hide_cutoff = now - timedelta(days=ITEM_TTL_DAYS)
    delete_cutoff = now - timedelta(days=ITEM_HARD_DELETE_DAYS)
    hidden = await db.agg_articles.update_many(
        {"published_at": {"$lt": hide_cutoff.isoformat()}, "hidden": {"$ne": True}},
        {"$set": {"hidden": True}},
    )
    deleted = await db.agg_articles.delete_many(
        {"published_at": {"$lt": delete_cutoff.isoformat()}},
    )
    return {"hidden": hidden.modified_count, "deleted": deleted.deleted_count}


async def test_feed(feed_url: str, display_mode: str = "headline_and_snippet") -> dict:
    """Used by /admin to validate a feed before activation. Returns the first
    3 parsed items so the operator can eyeball them."""
    if not _robots_allows(feed_url):
        return {"ok": False, "reason": "robots_disallowed", "items": []}
    xml, err = fetch_feed_xml(feed_url)
    if err:
        return {"ok": False, "reason": err, "items": []}
    try:
        entries = parse_entries(xml, {"display_mode": display_mode})
    except Exception as e:
        return {"ok": False, "reason": f"parse_error:{type(e).__name__}", "items": []}
    return {"ok": True, "count": len(entries), "items": entries[:3]}
