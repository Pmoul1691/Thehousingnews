"""Read-side helpers for the audience/contacts API.

Migration note (Feb 2026): File kept named `brevo_contacts.py` for
backward compatibility with `routes/admin_invite.py`. Internally it now
calls the Resend Audiences API instead of Brevo.

Resend models:
  - **Audience** ~ Brevo "list" (id is a UUID string, not an int)
  - **Contact** ~ Brevo contact, with first_name / last_name / unsubscribed
    flags exposed directly (no `attributes` envelope)

Docs: https://resend.com/docs/api-reference/audiences
      https://resend.com/docs/api-reference/contacts
"""
import logging
import os
from typing import Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_API_BASE = "https://api.resend.com"
HTTP_TIMEOUT = 20


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }


def list_brevo_lists() -> List[dict]:
    """Return every audience on the Resend account, formatted to match the
    legacy Brevo shape: `{id, name, totalSubscribers}`.

    Resend's `/audiences` endpoint does NOT return contact counts, so we
    call `/audiences/{id}/contacts` per audience to compute it. For large
    accounts this can be slow — admin_invite.py caches the preview result
    for 5 minutes so the cost is amortized.
    """
    if not RESEND_API_KEY:
        return []
    try:
        r = requests.get(
            f"{RESEND_API_BASE}/audiences",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("resend /audiences failed: %s %s", r.status_code, r.text[:200])
            return []
        audiences = (r.json() or {}).get("data") or []
    except Exception as e:
        logger.warning("resend /audiences exception: %s", e)
        return []

    out: List[dict] = []
    for a in audiences:
        aid = a.get("id")
        if not aid:
            continue
        total = 0
        try:
            rc = requests.get(
                f"{RESEND_API_BASE}/audiences/{aid}/contacts",
                headers=_headers(),
                timeout=HTTP_TIMEOUT,
            )
            if rc.status_code == 200:
                total = len((rc.json() or {}).get("data") or [])
        except Exception:
            pass
        out.append({
            "id": aid,
            "name": a.get("name") or "",
            "totalSubscribers": total,
            "created_at": a.get("created_at"),
        })
    return out


def find_list_by_name(name: str) -> Optional[dict]:
    """Case-insensitive match. Returns the first matching audience dict or None."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    for lst in list_brevo_lists():
        if (lst.get("name") or "").strip().lower() == needle:
            return lst
    return None


def iter_list_contacts(list_id, page_size: int = 500) -> Iterator[dict]:
    """Yield every contact from a Resend audience.

    `list_id` is a Resend audience UUID (string). The legacy Brevo signature
    accepted an int — we accept either and stringify.

    Resend currently returns ALL contacts in a single call (no offset/limit
    pagination on this endpoint), so `page_size` is accepted for signature
    compatibility but not used to chunk requests.
    """
    if not RESEND_API_KEY:
        return
    aid = str(list_id)
    try:
        r = requests.get(
            f"{RESEND_API_BASE}/audiences/{aid}/contacts",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning(
                "resend /audiences/%s/contacts failed: %s %s",
                aid, r.status_code, r.text[:200],
            )
            return
        for c in (r.json() or {}).get("data") or []:
            yield c
    except Exception as e:
        logger.warning("resend /audiences/%s/contacts exception: %s", aid, e)
        return


def normalize_contact(c: dict) -> dict:
    """Pull the fields we care about out of a Resend contact response.

    Resend shape: {id, email, first_name, last_name, unsubscribed, created_at, ...}
    Output shape preserved from Brevo era so admin_invite.py is untouched.
    """
    email = (c.get("email") or "").lower().strip()
    first = (c.get("first_name") or "").strip()
    last = (c.get("last_name") or "").strip()
    full = " ".join(p for p in [first, last] if p) or (email.split("@")[0] if email else "")
    unsubbed = bool(c.get("unsubscribed"))
    return {
        "email": email,
        "first_name": first,
        "last_name": last,
        "name": full,
        # Resend doesn't expose a "blacklisted" concept distinct from
        # unsubscribed — collapse both into the same flag.
        "blacklisted": unsubbed,
        "list_unsubscribed": unsubbed,
    }
