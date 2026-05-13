"""Parse YouTube/Vimeo URLs into a structured embed."""
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_VIMEO_HOSTS = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}


def parse_embed(url: str) -> Optional[dict]:
    """Return {provider, video_id, embed_url, thumbnail_url} or None if not supported."""
    if not url:
        return None
    try:
        u = urlparse(url.strip())
    except Exception:
        return None
    host = (u.hostname or "").lower()

    if host in _YOUTUBE_HOSTS:
        vid = None
        if host == "youtu.be":
            vid = u.path.lstrip("/").split("/")[0] or None
        elif u.path.startswith("/watch"):
            qs = parse_qs(u.query)
            vid = (qs.get("v") or [None])[0]
        elif u.path.startswith("/shorts/") or u.path.startswith("/embed/"):
            vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else None
        if not vid or not re.fullmatch(r"[\w-]{6,32}", vid):
            return None
        return {
            "provider": "youtube",
            "video_id": vid,
            "embed_url": f"https://www.youtube.com/embed/{vid}",
            "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        }

    if host in _VIMEO_HOSTS:
        # Path can be /<id> or /video/<id>
        parts = [p for p in u.path.split("/") if p]
        vid = None
        for p in parts:
            if p.isdigit():
                vid = p
                break
        if not vid:
            return None
        return {
            "provider": "vimeo",
            "video_id": vid,
            "embed_url": f"https://player.vimeo.com/video/{vid}",
            "thumbnail_url": None,
        }

    return None
