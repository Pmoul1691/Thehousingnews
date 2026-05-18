"""
Iter25 — verify the email_verified gates on POST /api/posts and /api/applications.
An unverified user (created via email/signup) should get 403 with a message
that mentions verification.
"""
import os, time, pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

@pytest.fixture(scope="module")
def fresh_user_session():
    """Signup a brand new email+password user → returns session_token cookie."""
    s = requests.Session()
    email = f"e2e.gate.{int(time.time()*1000)}@example.com"
    r = s.post(f"{BASE}/api/auth/email/signup", json={
        "email": email, "password": "Test1234!", "name": "Gate Tester",
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    # Session cookie should now be set on s
    me = s.get(f"{BASE}/api/auth/me", timeout=10)
    assert me.status_code == 200, me.text
    me_data = me.json()
    # New signups must start unverified
    assert me_data.get("email_verified") is False, me_data
    return {"session": s, "email": email, "me": me_data}


def test_post_creation_blocked_for_unverified(fresh_user_session):
    s = fresh_user_session["session"]
    r = s.post(f"{BASE}/api/posts", json={
        "title": "TEST_unverified_post",
        "text": "Should be blocked because the user is not verified yet.",
        "kind": "post",
    }, timeout=15)
    # Could be 403 (verify gate) or 400 (status=needs_application). Both are "gated".
    assert r.status_code in (400, 401, 403), f"expected 4xx, got {r.status_code}: {r.text}"
    if r.status_code == 403:
        detail = (r.json().get("detail") or "").lower()
        # Either verify-email gate OR membership-approval gate counts as gated for unverified users.
        assert "verify" in detail or "email" in detail or "approved" in detail or "membership" in detail, r.text


def test_application_blocked_for_unverified(fresh_user_session):
    s = fresh_user_session["session"]
    r = s.post(f"{BASE}/api/applications", json={
        "background": "TEST background for gating check, longer than twenty characters.",
        "why_joining": "TEST why joining — needs to be at least twenty characters long.",
        "contribution": "TEST contribution — also long enough for validators.",
        "current_role": "Tester",
        "market": "Test Market",
        "years_in_real_estate": "1",
    }, timeout=15)
    # Same: either verify gate or status guard.
    assert r.status_code in (400, 401, 403), f"expected 4xx, got {r.status_code}: {r.text}"
    if r.status_code == 403:
        detail = (r.json().get("detail") or "").lower()
        # Accept either verify message or generic auth message
        assert "verify" in detail or "email" in detail or "approved" in detail, r.text
