"""Guardrails for outbound email URL stamping.

After an incident where briefs went out with a stale Emergent preview URL
stamped into the 'Open The Daily' button (sending members to a pre-pivot
snapshot of the site), brevo.py grew two protections:

  1. app_url() hard-defaults to the production host when APP_PUBLIC_URL is
     missing or empty.
  2. send_email() refuses to send any email whose HTML body links to a
     preview.emergentagent.com URL.

This file locks both behaviours in.
"""
import importlib
import os

import pytest


@pytest.fixture
def brevo(monkeypatch):
    """Import brevo with APP_PUBLIC_URL unset so we exercise the default."""
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "test-key")  # bypass the "missing key" skip
    import services.brevo as b
    importlib.reload(b)
    return b


def test_app_url_defaults_to_production_when_env_missing(brevo):
    assert brevo.app_url() == "https://thehousingnews.com"


def test_app_url_defaults_to_production_when_env_empty(monkeypatch, brevo):
    monkeypatch.setenv("APP_PUBLIC_URL", "")
    importlib.reload(brevo)
    assert brevo.app_url() == "https://thehousingnews.com"


def test_app_url_strips_trailing_slash(monkeypatch, brevo):
    monkeypatch.setenv("APP_PUBLIC_URL", "https://thehousingnews.com/")
    importlib.reload(brevo)
    assert brevo.app_url() == "https://thehousingnews.com"


def test_app_url_uses_env_when_set(monkeypatch, brevo):
    monkeypatch.setenv("APP_PUBLIC_URL", "https://staging.thehousingnews.com")
    importlib.reload(brevo)
    assert brevo.app_url() == "https://staging.thehousingnews.com"


def test_send_email_refuses_preview_url_in_body(brevo, monkeypatch):
    """If the html body somehow contains a preview URL, refuse to send."""
    sent = {}

    def fake_post(*args, **kwargs):
        sent["called"] = True
        raise AssertionError("requests.post must not be called when body has a preview URL")

    monkeypatch.setattr(brevo.requests, "post", fake_post)

    poisoned = (
        '<a href="https://housing-news-perf.preview.emergentagent.com/news">Open The Daily</a>'
    )
    result = brevo.send_email(
        to_email="test@example.com",
        to_name="Test",
        subject="hi",
        html=poisoned,
    )
    assert result.get("blocked") is True
    assert "preview URL" in result.get("error", "")
    assert "called" not in sent


def test_send_email_allows_clean_html(brevo, monkeypatch):
    """A normal production URL in the body sends through to Resend."""
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):  # noqa: D401
            return {"id": "abc"}

    def fake_post(url, json, headers, timeout):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(brevo.requests, "post", fake_post)

    clean = '<a href="https://thehousingnews.com/news">Open The Daily</a>'
    result = brevo.send_email(
        to_email="test@example.com",
        to_name="Test",
        subject="hi",
        html=clean,
    )
    assert result == {"id": "abc"}
    assert "/emails" in captured["url"]
    assert "api.resend.com" in captured["url"]
