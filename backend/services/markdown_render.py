"""Markdown -> sanitized HTML for essay emails and any server-side rendering needs."""
import markdown as md_lib
import bleach

# Allowed tags & attributes for essay HTML. Conservative.
ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "p", "br", "hr",
    "em", "strong", "i", "b", "u", "code", "pre", "blockquote",
    "ul", "ol", "li",
    "a", "img",
]
ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
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
