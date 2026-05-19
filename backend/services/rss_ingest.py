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
FETCH_TIMEOUT_SECONDS = 10

# Tracking-param patterns stripped from canonical article URLs so the same
# article shared with utm_* / fbclid / gclid / mc_* etc. doesn't double-store.
_TRACKING_PARAM_PREFIXES = ("utm_", "mc_", "_hs", "hsa_", "ref_", "vero_", "pk_")
_TRACKING_PARAM_EXACT = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "wbraid", "gbraid",
    "ref", "source", "src", "share", "share_id", "feature",
    "mc_cid", "mc_eid",
}


def normalize_url(url: str) -> str:
    """Return a canonical form of `url` for dedup purposes:
    - scheme + host lowercased
    - host stripped of leading `www.`
    - trailing slash removed
    - all utm_*, fbclid, gclid, etc. query params dropped
    - remaining query params sorted alphabetically
    - fragment dropped
    Returns the input unchanged if parsing fails.
    """
    if not url:
        return url
    try:
        from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
        p = urlparse(url.strip())
        if not p.scheme or not p.netloc:
            return url.strip().lower()
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = (p.path or "/").rstrip("/") or "/"
        kept = []
        for k, v in parse_qsl(p.query, keep_blank_values=False):
            kl = k.lower()
            if kl in _TRACKING_PARAM_EXACT:
                continue
            if any(kl.startswith(pref) for pref in _TRACKING_PARAM_PREFIXES):
                continue
            kept.append((k, v))
        kept.sort()
        return urlunparse((p.scheme.lower(), host, path, "", urlencode(kept), ""))
    except Exception:
        return url.strip().lower()


# ---------- Title-based fuzzy dedup ----------
#
# Two publishers often re-share the same wire story with slightly different
# titles ("Fed signals rate cut" vs "Fed Signals Rate Cut In June - WSJ").
# We strip the publisher suffix, common prefixes ("BREAKING:", "EXCLUSIVE:"),
# punctuation, and stop-words, then store a `title_signature`. New inserts
# check the last 48h for any article with the same signature OR a high
# difflib similarity ratio and skip the duplicate.

# Trailing "delimiter Publisher" suffix patterns. The em/en/regular hyphen,
# pipe, middle-dot and bullet are all in use across our 28 publishers.
_TITLE_SUFFIX_RE = re.compile(
    r"\s*[\|\-\u2013\u2014\u00B7\u2022:]\s*[^\|\-\u2013\u2014\u00B7\u2022]{2,40}\s*$"
)
_TITLE_PREFIX_RE = re.compile(
    r"^\s*(breaking|exclusive|opinion|analysis|update|video|watch|live|just in)\s*[:\-\u2013\u2014]\s*",
    re.IGNORECASE,
)
# Stop-words that don't help distinguish stories.
_TITLE_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "as", "is", "are", "was", "were", "be", "by",
}
_TITLE_FUZZY_RATIO = 0.88  # difflib similarity above this counts as dup
_TITLE_FUZZY_WINDOW_HOURS = 48  # only compare against recent articles


def normalize_title(title: str) -> str:
    """Strip publisher suffix, prefix labels, punctuation and stop-words so
    near-identical wire stories collapse to the same signature.
    """
    if not title:
        return ""
    t = title.strip()
    # Drop leading "BREAKING:", "EXCLUSIVE:", etc. FIRST so we don't mistake
    # the body of a short headline for a publisher suffix below.
    t = _TITLE_PREFIX_RE.sub("", t)
    # Drop trailing " - Publisher Name", " | Bloomberg", etc. — but only when
    # there's enough body before the delimiter to confidently say the suffix
    # is publisher branding, not the article itself (e.g. "Fed - WSJ" stays).
    m = _TITLE_SUFFIX_RE.search(t)
    if m and m.start() >= 8:
        t = t[: m.start()]
    t = t.lower()
    # Replace any non-alphanumeric run with single space
    t = re.sub(r"[^a-z0-9]+", " ", t)
    tokens = [w for w in t.split() if w and w not in _TITLE_STOPWORDS]
    return " ".join(tokens)


def title_signature(title: str) -> str:
    """Stable short hash of the normalized title for index lookups."""
    import hashlib
    norm = normalize_title(title)
    if not norm:
        return ""
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def titles_are_near_duplicates(a: str, b: str) -> bool:
    """Return True when two NORMALIZED titles look like the same story.
    Cheap path: exact equality. Borderline: difflib ratio >= threshold."""
    if not a or not b:
        return False
    if a == b:
        return True
    if abs(len(a) - len(b)) > max(8, int(0.4 * min(len(a), len(b)))):
        return False
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() >= _TITLE_FUZZY_RATIO


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


def fetch_feed_xml(feed_url: str, user_agent: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Returns (xml_text, error_str). error_str is None on success."""
    ua = user_agent or USER_AGENT
    try:
        r = requests.get(
            feed_url,
            headers={"User-Agent": ua, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
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
            "author": (entry.get("author") or "").strip(),
        })
    return out


async def ingest_publisher(db, publisher: dict) -> dict:
    """Fetch + parse a single publisher. Updates Mongo and returns a tiny stats
    dict. Wrapped by callers in try/except so one bad feed never affects others."""
    pub_id = publisher["id"]
    feed_url = publisher["feed_url"]
    custom_ua = publisher.get("user_agent")
    bypass_robots = bool(publisher.get("bypass_robots"))

    # robots.txt (skippable per publisher when bypass_robots is set; used for
    # sources where we have a separate editorial decision to ingest).
    if not bypass_robots and not _robots_allows(feed_url):
        await db.agg_publishers.update_one(
            {"id": pub_id},
            {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": "robots_disallowed"},
             "$inc": {"error_count": 1}},
        )
        return {"publisher_id": pub_id, "ok": False, "reason": "robots_disallowed", "inserted": 0}

    xml, err = fetch_feed_xml(feed_url, user_agent=custom_ua)
    if err:
        await db.agg_publishers.update_one(
            {"id": pub_id},
            {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": err},
             "$inc": {"error_count": 1}},
        )
        return {"publisher_id": pub_id, "ok": False, "reason": err, "inserted": 0}

    try:
        entries = parse_entries(xml, publisher)
    except Exception as e:
        logger.exception("parse failure for %s: %s", pub_id, e)
        await db.agg_publishers.update_one(
            {"id": pub_id},
            {"$set": {"last_fetched_at": _now_iso(), "last_fetch_status": f"parse_error:{type(e).__name__}"},
             "$inc": {"error_count": 1}},
        )
        return {"publisher_id": pub_id, "ok": False, "reason": "parse_error", "inserted": 0}

    # Optional per-publisher keyword filter — used for mixed-topic feeds (e.g.
    # TheStreet's full firehose) where we only want housing-relevant items.
    # Matches on word boundaries so short keywords don't trigger false positives.
    keywords = publisher.get("keyword_filter") or []
    if keywords:
        kw_pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(k) for k in keywords) + r")\b",
            re.IGNORECASE,
        )
        before = len(entries)
        entries = [e for e in entries if kw_pattern.search(e.get("title", ""))]
        logger.info("keyword filter for %s: %d/%d kept", pub_id, len(entries), before)

    # Optional per-publisher exclude patterns — title regex blocklist used for
    # Reddit-sourced feeds to drop fluff/celebration/help-me threads.
    excludes = publisher.get("exclude_patterns") or []
    if excludes:
        ex_pattern = re.compile("|".join(excludes), re.IGNORECASE)
        before = len(entries)
        entries = [e for e in entries if not ex_pattern.search(e.get("title", ""))]
        logger.info("exclude filter for %s: %d/%d kept", pub_id, len(entries), before)

    # Reddit-specific: drop AutoModerator posts (announcements / weekly threads).
    if (publisher.get("source_type") or "") == "reddit":
        before = len(entries)
        entries = [e for e in entries if "automoderator" not in (e.get("author") or "").lower()]
        if len(entries) != before:
            logger.info("automod filter for %s: %d/%d kept", pub_id, len(entries), before)

    inserted = 0
    skipped = 0
    skipped_title_dup = 0
    fetched_at = _now_iso()
    # Cache of recent normalized titles for in-batch dedup (catches two
    # articles arriving in the same fetch that point to different URLs but
    # are the same wire story).
    seen_norm_titles: list[str] = []
    fuzzy_cutoff = _now() - timedelta(hours=_TITLE_FUZZY_WINDOW_HOURS)
    for art in entries:
        published_at = datetime.fromisoformat(art["published_at"])
        expires_at = published_at + timedelta(days=ITEM_TTL_DAYS)
        # Dedupe key: normalized_url (utm_*/fbclid/gclid stripped). Falls back
        # to (publisher_id, guid) on the secondary index for legacy rows.
        guid = art["guid"] or art["original_url"]
        norm_url = normalize_url(art["original_url"])
        norm_title = normalize_title(art["title"])
        title_sig = title_signature(art["title"])

        # Secondary dedup: same wire story re-titled by a different publisher.
        # Only kicks in when the publisher_id differs (we trust the source's
        # own titling for its own URL).
        if norm_title:
            # 1) Cheap path: exact signature match within the fuzzy window,
            #    from a DIFFERENT publisher.
            dup = await db.agg_articles.find_one(
                {
                    "title_signature": title_sig,
                    "publisher_id": {"$ne": pub_id},
                    "published_at": {"$gte": fuzzy_cutoff.isoformat()},
                },
                {"_id": 0, "id": 1},
            )
            if dup is None:
                # 2) Borderline: scan recent same-window titles for a fuzzy
                #    match. Bounded scan (200 rows) keeps this O(1) practically.
                recent_cur = db.agg_articles.find(
                    {
                        "publisher_id": {"$ne": pub_id},
                        "published_at": {"$gte": fuzzy_cutoff.isoformat()},
                        "title_signature": {"$ne": title_sig},
                    },
                    {"_id": 0, "title_normalized": 1},
                ).limit(200)
                async for r in recent_cur:
                    if titles_are_near_duplicates(norm_title, r.get("title_normalized") or ""):
                        dup = r
                        break
                # 3) Also catch dupes inside the same fetch batch.
                if dup is None:
                    for cached in seen_norm_titles:
                        if titles_are_near_duplicates(norm_title, cached):
                            dup = {"in_batch": True}
                            break
            if dup is not None:
                skipped_title_dup += 1
                continue
            seen_norm_titles.append(norm_title)

        doc = {
            "id": str(uuid.uuid4()),
            "publisher_id": pub_id,
            "guid": guid,
            "title": art["title"],
            "title_normalized": norm_title,
            "title_signature": title_sig,
            "snippet": art["snippet"],
            "thumbnail_url": art["thumbnail_url"],
            "original_url": art["original_url"],
            "normalized_url": norm_url,
            "published_at": art["published_at"],
            "fetched_at": fetched_at,
            "expires_at": expires_at.isoformat(),
            "hidden": False,
            "created_at": _now_iso(),
        }
        # Primary dedup: normalized URL across all publishers (same story re-shared
        # with different tracking params won't double-store).
        try:
            res = await db.agg_articles.update_one(
                {"normalized_url": norm_url},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning("article upsert failed (pub=%s url=%s): %s", pub_id, norm_url, e)

    await db.agg_publishers.update_one(
        {"id": pub_id},
        {"$set": {"last_fetched_at": fetched_at, "last_fetch_status": "ok", "error_count": 0}},
    )
    return {
        "publisher_id": pub_id,
        "ok": True,
        "inserted": inserted,
        "skipped": skipped,
        "skipped_title_dup": skipped_title_dup,
        "parsed": len(entries),
    }


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
