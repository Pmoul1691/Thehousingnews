"""Compute the SHA-256 hash of the Terms of Service PDF served at
`/legal/terms-of-service.pdf`. Stamped on every application submission so we
can prove which version of the document each member accepted.

The hash is computed lazily on first call and cached. Falls back to "unknown"
if the file is missing — application submission still succeeds, but no hash
is recorded.
"""
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path is fixed relative to repo root: /app/frontend/public/legal/terms-of-service.pdf
TOS_PDF_PATH = Path("/app/frontend/public/legal/terms-of-service.pdf")
TOS_PUBLIC_URL = "/legal/terms-of-service.pdf"

_HASH_CACHE: dict = {}


def tos_version_hash() -> str:
    """SHA-256 hex of the ToS PDF. Cached per file mtime so we automatically
    pick up a new hash if the PDF is replaced without restarting the server."""
    try:
        mtime = TOS_PDF_PATH.stat().st_mtime
    except FileNotFoundError:
        logger.warning("ToS PDF not found at %s", TOS_PDF_PATH)
        return "unknown"
    cached = _HASH_CACHE.get("entry")
    if cached and cached["mtime"] == mtime:
        return cached["hash"]
    h = hashlib.sha256()
    with TOS_PDF_PATH.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _HASH_CACHE["entry"] = {"mtime": mtime, "hash": digest}
    return digest
