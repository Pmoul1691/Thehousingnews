"""Tests for the public aggregator: ingestion service, snippet cap, dedupe,
and the public read endpoints."""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.rss_ingest import _strip_html, _truncate_snippet, parse_entries


def test_strip_html_removes_tags_and_collapses_whitespace():
    raw = "<p>Hello\n  <strong>world</strong>!</p><img src=x>"
    out = _strip_html(raw)
    assert out == "Hello world !" or out == "Hello world!"


def test_truncate_snippet_caps_at_280_chars():
    long = "Sentence one is short. " + ("A" * 400)
    out = _truncate_snippet(long)
    assert len(out) <= 283  # 280 + "..." ellipsis
    assert out.endswith("...") or len(out) <= 280


def test_truncate_snippet_caps_at_two_sentences():
    text = "One. Two. Three. Four. Five."
    out = _truncate_snippet(text)
    # Two sentences only
    assert out.count(".") == 2
    assert "Three" not in out


def test_truncate_snippet_empty_input():
    assert _truncate_snippet("") == ""
    assert _truncate_snippet(None) == ""


def test_parse_entries_respects_headline_only_display_mode():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>X</title>
<item>
  <title>Big headline goes here</title>
  <link>https://example.com/a1</link>
  <description>This is the snippet that should not appear because mode is headline_only.</description>
  <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
  <guid>https://example.com/a1</guid>
</item>
</channel></rss>"""
    entries = parse_entries(xml, {"display_mode": "headline_only"})
    assert len(entries) == 1
    e = entries[0]
    assert e["title"] == "Big headline goes here"
    assert e["snippet"] == ""
    assert e["original_url"] == "https://example.com/a1"


def test_parse_entries_returns_snippet_when_headline_and_snippet_mode():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>X</title>
<item>
  <title>Headline</title>
  <link>https://example.com/a2</link>
  <description>First sentence here. Second sentence here. Third sentence ignored.</description>
  <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
  <guid>https://example.com/a2</guid>
</item>
</channel></rss>"""
    entries = parse_entries(xml, {"display_mode": "headline_and_snippet"})
    assert len(entries) == 1
    snip = entries[0]["snippet"]
    assert "First sentence here" in snip
    assert "Second sentence here" in snip
    assert "Third sentence" not in snip


def test_parse_entries_extracts_thumbnail_from_enclosure():
    xml = """<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>X</title>
<item>
  <title>With image</title>
  <link>https://example.com/a3</link>
  <enclosure url="https://cdn.example.com/img.jpg" type="image/jpeg" />
  <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
  <guid>https://example.com/a3</guid>
</item>
</channel></rss>"""
    entries = parse_entries(xml, {"display_mode": "headline_and_snippet"})
    assert entries[0]["thumbnail_url"] == "https://cdn.example.com/img.jpg"


def test_parse_entries_no_image_returns_none():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>X</title>
<item>
  <title>Plain</title>
  <link>https://example.com/a4</link>
  <pubDate>Wed, 14 May 2026 12:00:00 GMT</pubDate>
  <guid>https://example.com/a4</guid>
</item>
</channel></rss>"""
    entries = parse_entries(xml, {"display_mode": "headline_and_snippet"})
    assert entries[0]["thumbnail_url"] is None


def test_parse_entries_skips_items_missing_title_or_link():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>X</title>
<item><link>https://example.com/no-title</link></item>
<item><title>No link</title></item>
<item><title>Both</title><link>https://example.com/ok</link></item>
</channel></rss>"""
    entries = parse_entries(xml, {"display_mode": "headline_and_snippet"})
    assert len(entries) == 1
    assert entries[0]["title"] == "Both"
