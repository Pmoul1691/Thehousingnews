"""EnrichLayer (Proxycurl successor) LinkedIn profile lookups.

Single-purpose service. Pulls a LinkedIn profile by URL and returns a small,
normalised dict ready to merge into our `profiles` collection.

Cost: 1–3 EnrichLayer credits per call. Cache-friendly (`use_cache=if-present`)
so repeat lookups within EL's cache window are free.
"""
import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EL_BASE = "https://enrichlayer.com/api/v2"
EL_TIMEOUT = 25.0


class LinkedInImportError(Exception):
    pass


def _api_key() -> str:
    k = os.environ.get("ENRICHLAYER_API_KEY")
    if not k:
        raise LinkedInImportError("ENRICHLAYER_API_KEY not configured")
    return k


def _experiences(raw: list[dict]) -> list[dict]:
    out = []
    for e in raw or []:
        out.append({
            "company": e.get("company") or "",
            "title": e.get("title") or "",
            "starts_at": (e.get("starts_at") or {}).get("year"),
            "ends_at": (e.get("ends_at") or {}).get("year"),
            "location": e.get("location"),
            "description": e.get("description"),
        })
    return out


def _education(raw: list[dict]) -> list[dict]:
    out = []
    for e in raw or []:
        out.append({
            "school": e.get("school") or "",
            "degree": e.get("degree_name"),
            "field": e.get("field_of_study"),
            "starts_at": (e.get("starts_at") or {}).get("year"),
            "ends_at": (e.get("ends_at") or {}).get("year"),
        })
    return out


def _city_state(raw: dict) -> Optional[str]:
    city = raw.get("city")
    state = raw.get("state")
    if city and state:
        return f"{city}, {state}"
    return city or state or None


def fetch_linkedin_profile(linkedin_url: str) -> dict:
    """Hit EnrichLayer and return a normalised profile dict.

    Raises LinkedInImportError on any failure (network, auth, 4xx, parse).
    """
    if not linkedin_url:
        raise LinkedInImportError("linkedin_url is required")

    key = _api_key()
    try:
        r = httpx.get(
            f"{EL_BASE}/profile",
            params={
                "profile_url": linkedin_url,
                "use_cache": "if-present",
                "fallback_to_cache": "on-error",
            },
            headers={"Authorization": f"Bearer {key}"},
            timeout=EL_TIMEOUT,
        )
    except httpx.RequestError as exc:
        logger.exception("EnrichLayer request failed")
        raise LinkedInImportError(f"Network error: {exc}") from exc

    if r.status_code == 401:
        raise LinkedInImportError("EnrichLayer rejected the API key (401)")
    if r.status_code == 402:
        raise LinkedInImportError("EnrichLayer account is out of credits (402)")
    if r.status_code == 404:
        raise LinkedInImportError("LinkedIn profile not found")
    if r.status_code >= 400:
        raise LinkedInImportError(f"EnrichLayer error {r.status_code}: {r.text[:200]}")

    try:
        d = r.json()
    except ValueError as exc:
        raise LinkedInImportError("EnrichLayer returned non-JSON response") from exc

    if isinstance(d, dict) and d.get("code") and int(d.get("code", 0)) >= 400:
        raise LinkedInImportError(d.get("description") or "EnrichLayer error")

    return {
        "linkedin_url": linkedin_url,
        "public_identifier": d.get("public_identifier"),
        "full_name": d.get("full_name") or "",
        "first_name": d.get("first_name") or "",
        "last_name": d.get("last_name") or "",
        "headline": d.get("headline") or "",
        "occupation": d.get("occupation") or "",
        "summary": d.get("summary") or "",
        "city": d.get("city"),
        "state": d.get("state"),
        "country": d.get("country"),
        "location": _city_state(d),
        "profile_pic_url": d.get("profile_pic_url"),
        "experiences": _experiences(d.get("experiences") or []),
        "education": _education(d.get("education") or []),
        "follower_count": d.get("follower_count"),
    }
