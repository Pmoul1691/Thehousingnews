"""Read-side helpers for the Brevo Contacts API.

Used by the admin "bulk invite" tool: fetch contacts from a named list, page
through them, and surface the attributes we want to personalize the invite
email (first name, full name, email).

Docs: https://developers.brevo.com/reference/getcontactsfromlist
"""
import logging
import os
from typing import Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
API_BASE = "https://api.brevo.com/v3"
HTTP_TIMEOUT = 20


def _headers() -> dict:
    return {
        "accept": "application/json",
        "api-key": BREVO_API_KEY or "",
    }


def list_brevo_lists() -> List[dict]:
    """Return every list on the Brevo account: [{id, name, totalSubscribers, ...}]."""
    if not BREVO_API_KEY:
        return []
    out: List[dict] = []
    offset = 0
    while True:
        r = requests.get(
            f"{API_BASE}/contacts/lists",
            headers=_headers(),
            params={"limit": 50, "offset": offset, "sort": "desc"},
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("brevo /contacts/lists failed: %s %s", r.status_code, r.text[:200])
            break
        data = r.json()
        lists = data.get("lists") or []
        out.extend(lists)
        if len(lists) < 50:
            break
        offset += 50
    return out


def find_list_by_name(name: str) -> Optional[dict]:
    """Case-insensitive match. Returns the first matching list dict or None."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    for lst in list_brevo_lists():
        if (lst.get("name") or "").strip().lower() == needle:
            return lst
    return None


def iter_list_contacts(list_id: int, page_size: int = 500) -> Iterator[dict]:
    """Yield every contact from a Brevo list. Each contact is the raw dict
    Brevo returns: {id, email, attributes: {FIRSTNAME, LASTNAME, ...}, ...}.

    Page size is Brevo's max (500) to minimize round-trips on large lists."""
    if not BREVO_API_KEY:
        return
    offset = 0
    while True:
        r = requests.get(
            f"{API_BASE}/contacts/lists/{list_id}/contacts",
            headers=_headers(),
            params={"limit": page_size, "offset": offset, "sort": "desc"},
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning(
                "brevo /contacts/lists/%s/contacts failed: %s %s",
                list_id, r.status_code, r.text[:200],
            )
            return
        data = r.json()
        contacts = data.get("contacts") or []
        for c in contacts:
            yield c
        if len(contacts) < page_size:
            return
        offset += page_size


def normalize_contact(c: dict) -> dict:
    """Pull the fields we care about out of a Brevo contact response."""
    email = (c.get("email") or "").lower().strip()
    attrs = c.get("attributes") or {}
    first = (attrs.get("FIRSTNAME") or attrs.get("FIRST_NAME") or "").strip()
    last = (attrs.get("LASTNAME") or attrs.get("LAST_NAME") or "").strip()
    full = " ".join(p for p in [first, last] if p) or (email.split("@")[0] if email else "")
    return {
        "email": email,
        "first_name": first,
        "last_name": last,
        "name": full,
        "blacklisted": bool(c.get("emailBlacklisted")),
        "list_unsubscribed": bool(c.get("listUnsubscribed")),
    }
