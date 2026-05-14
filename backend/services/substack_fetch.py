"""Fetch the original Substack page for an imported essay and extract its
Mux video metadata. Substack publishes video posts where the RSS only
delivers the short text caption - the actual content is a Mux-hosted video
embedded on the post page. This service pulls the Mux `playback_id` so the
reader page can stream the full video inline.
"""
import json
import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_VIDEO_UPLOAD_RE = re.compile(r'"videoUpload":(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})')


def _safe_json_chunk(text: str, start: int) -> Optional[dict]:
    depth = 0
    end = start
    in_str = False
    esc = False
    for i in range(start, min(len(text), start + 8000)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    try:
        return json.loads(text[start:end])
    except Exception:
        return None


def fetch_substack_media(post_url: str, timeout: int = 10) -> Optional[dict]:
    """Return a media dict for the post if it embeds a Mux video, else None.

    Shape:
      {
        "kind": "video",
        "external_hls_url": "https://stream.mux.com/{id}.m3u8",
        "poster_url": "https://image.mux.com/{id}/thumbnail.jpg",
        "duration_s": float,
        "width": int,
        "height": int,
      }
    """
    if not post_url:
        return None
    try:
        r = requests.get(
            post_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; UltradianBot/1.0)"},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        html = r.text
    except Exception as e:
        logger.warning("Substack fetch failed for %s: %s", post_url, e)
        return None

    # Substack inlines its post data as escaped JSON inside a JS hydration
    # blob, so we look for the escaped key form first and fall back to plain.
    idx = html.find('\\"videoUpload\\":')
    if idx < 0:
        idx = html.find('"videoUpload":')
    if idx < 0:
        return None
    region = html[idx: idx + 4000]
    pb = re.search(r'\\?"mux_playback_id\\?":\\?"([^"\\\\]+)\\?"', region)
    if not pb:
        return None
    playback_id = pb.group(1)
    duration_m = re.search(r'\\?"duration\\?":\s*([\d.]+)', region)
    width_m = re.search(r'\\?"width\\?":\s*(\d+)', region)
    height_m = re.search(r'\\?"height\\?":\s*(\d+)', region)
    return {
        "kind": "video",
        "external_hls_url": f"https://stream.mux.com/{playback_id}.m3u8",
        "poster_url": f"https://image.mux.com/{playback_id}/thumbnail.jpg",
        "duration_s": float(duration_m.group(1)) if duration_m else 0.0,
        "width": int(width_m.group(1)) if width_m else 0,
        "height": int(height_m.group(1)) if height_m else 0,
        "source": "substack_mux",
    }
