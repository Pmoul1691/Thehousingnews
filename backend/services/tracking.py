"""Email tracking: HTML wrapping with open pixel and link rewriting."""
import os
import re
import logging
from urllib.parse import quote
from typing import Optional

logger = logging.getLogger(__name__)


def _base_url() -> str:
    # APP_PUBLIC_URL is the canonical external base (e.g. https://ultradiannetwork.com)
    return os.environ.get("APP_PUBLIC_URL", "").rstrip("/")


def wrap_for_tracking(html: str, dispatch_id: Optional[str]) -> str:
    """Insert a 1x1 open pixel and rewrite every <a href="https://..."> to a click-tracking redirect.

    No-op when dispatch_id is empty or APP_PUBLIC_URL is not configured.
    """
    if not dispatch_id:
        return html
    base = _base_url()
    if not base:
        return html

    # Rewrite anchor hrefs. Only http(s) external links, never mailto: or anchors.
    href_pattern = re.compile(r'(<a\b[^>]*\bhref=")([^"]+)(")', flags=re.IGNORECASE)

    def _rewrite(match):
        prefix, url, suffix = match.group(1), match.group(2), match.group(3)
        # Skip anchors, mailto, tel, javascript, already-tracked, and the pixel itself
        if (
            not url
            or url.startswith("#")
            or url.startswith("mailto:")
            or url.startswith("tel:")
            or url.startswith("javascript:")
            or "/api/track/click/" in url
        ):
            return match.group(0)
        wrapped = f"{base}/api/track/click/{dispatch_id}?to={quote(url, safe='')}"
        return f"{prefix}{wrapped}{suffix}"

    wrapped = href_pattern.sub(_rewrite, html)

    pixel = (
        f'<img src="{base}/api/track/open/{dispatch_id}.gif" alt="" '
        f'width="1" height="1" style="display:block; width:1px; height:1px; border:0;" />'
    )
    # Place the pixel right before </body> if present, else just append
    if "</body>" in wrapped.lower():
        idx = wrapped.lower().rindex("</body>")
        wrapped = wrapped[:idx] + pixel + wrapped[idx:]
    else:
        wrapped = wrapped + pixel
    return wrapped
