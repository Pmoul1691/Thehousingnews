"""Personal Access Tokens (PATs).

Lightweight token system for programmatic posting (e.g., a Claude integration
that drafts posts and POSTs to /api/posts via Authorization: Bearer thn_pat_*).

Design choices kept intentionally simple per user request:
- One token per call (no scopes); a PAT has the same write power its owner has.
- Tokens are shown to the user exactly once at creation. We store a SHA-256
  hash + a short 12-char prefix only. The prefix is what the user sees in lists
  so they can recognize which key is which.
- Revocation is soft: we set `revoked_at`; the auth check rejects any PAT with
  a non-null `revoked_at`. Rows stick around for audit.

Token format: `thn_pat_<32-char base32 alphabet>` — total length 40.
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

PAT_PREFIX = "thn_pat_"
PAT_BODY_LEN = 32  # base32 chars after the prefix
PAT_DISPLAY_PREFIX_LEN = 12  # how much of the raw token we store/show as `prefix`

# Available PAT scopes. A token with no scopes (or the special `*` value)
# inherits its owner's full permissions — the current default for any token
# minted before this field existed.
KNOWN_SCOPES = ("posts:write", "essays:write", "profile:write")
SCOPE_ALL = "*"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """Return a freshly-generated PAT in `thn_pat_<32>` form."""
    body = secrets.token_urlsafe(32)[:PAT_BODY_LEN]
    return f"{PAT_PREFIX}{body}"


def looks_like_pat(token: Optional[str]) -> bool:
    return bool(token and token.startswith(PAT_PREFIX))


async def resolve_pat(db, raw_token: str) -> Optional[dict]:
    """Given a raw PAT string, return the owning user dict (or None if invalid
    / revoked / orphaned). Also stamps `last_used_at` on the PAT row.

    Never raises — callers fall back to the legacy session-token path.
    """
    if not looks_like_pat(raw_token):
        return None
    prefix = raw_token[: PAT_DISPLAY_PREFIX_LEN]
    pat = await db.pats.find_one({"prefix": prefix, "revoked_at": None}, {"_id": 0})
    if not pat:
        return None
    if pat.get("token_hash") != _hash_token(raw_token):
        return None
    user = await db.users.find_one({"user_id": pat["user_id"]}, {"_id": 0})
    if not user:
        return None
    # Best-effort stamp; never fail the request if this update fails.
    try:
        await db.pats.update_one({"id": pat["id"]}, {"$set": {"last_used_at": _now_iso()}})
    except Exception:
        logger.exception("pat last_used_at stamp failed for prefix=%s", prefix)
    # Attach scopes so downstream require_scope() helpers can enforce them
    # without re-querying. Sessions tokens (non-PAT) have no `_pat_scopes`,
    # which means they keep full access.
    user = dict(user)
    user["_pat_id"] = pat["id"]
    user["_pat_scopes"] = pat.get("scopes") or [SCOPE_ALL]
    return user


def pat_has_scope(user: dict, required: str) -> bool:
    """Return True if the resolving credential is allowed to perform `required`.

    A standard session-token request has no `_pat_scopes` and is always allowed.
    A PAT-resolved user must have either the literal scope or `*` in its list.
    """
    scopes = user.get("_pat_scopes")
    if scopes is None:
        return True  # session-token caller
    return SCOPE_ALL in scopes or required in scopes


async def create_pat(db, user_id: str, name: str, scopes: Optional[list] = None) -> dict:
    """Create a new PAT for `user_id`. Returns the row PLUS the raw token (the
    only time the raw token is ever exposed). Caller must show it once and
    discard.

    `scopes` is an optional list of strings from KNOWN_SCOPES. Empty/None
    defaults to full access ([`*`]).
    """
    raw = generate_token()
    if not scopes:
        normalized = [SCOPE_ALL]
    else:
        normalized = sorted({s for s in scopes if s == SCOPE_ALL or s in KNOWN_SCOPES})
        if not normalized:
            normalized = [SCOPE_ALL]
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": (name or "").strip()[:80] or "Unnamed token",
        "prefix": raw[:PAT_DISPLAY_PREFIX_LEN],
        "token_hash": _hash_token(raw),
        "scopes": normalized,
        "created_at": _now_iso(),
        "last_used_at": None,
        "revoked_at": None,
    }
    await db.pats.insert_one(row)
    # Mongo's insert_one mutates `row` in place to add `_id` (ObjectId, not
    # JSON-serializable). Strip it before responding.
    row.pop("_id", None)
    out = {k: v for k, v in row.items() if k != "token_hash"}
    out["token"] = raw  # ONCE
    return out


def public_pat_view(row: dict) -> dict:
    """Strip secrets from a stored PAT row for listing."""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "prefix": row.get("prefix"),
        "scopes": row.get("scopes") or [SCOPE_ALL],
        "created_at": row.get("created_at"),
        "last_used_at": row.get("last_used_at"),
        "revoked_at": row.get("revoked_at"),
    }
