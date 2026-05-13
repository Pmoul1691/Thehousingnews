"""Markdown -> sanitized HTML for essay emails and any server-side rendering needs."""
import markdown as md_lib
import bleach

# Allowed tags & attributes for essay HTML. Conservative but now supports inline
# video / audio / iframe media inserted from the rich-text editor.
ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "p", "br", "hr", "div", "span",
    "em", "strong", "i", "b", "u", "code", "pre", "blockquote",
    "ul", "ol", "li",
    "a", "img",
    "video", "audio", "source", "iframe",
]
ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "video": ["src", "controls", "poster", "preload", "playsinline", "style", "width", "height"],
    "audio": ["src", "controls", "preload", "style"],
    "source": ["src", "type"],
    "iframe": ["src", "width", "height", "frameborder", "allow", "allowfullscreen", "title", "loading"],
}


def render(md_text: str) -> str:
    """Convert markdown to safe HTML."""
    if not md_text:
        return ""
    html = md_lib.markdown(
        md_text,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html",
    )
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https", "mailto"], strip=True)
