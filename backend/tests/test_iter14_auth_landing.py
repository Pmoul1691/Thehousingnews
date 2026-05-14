"""Iteration 14 - Auth flow (Authorization Bearer) + Landing public endpoints."""
import os
import time
import uuid
import requests
import subprocess

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Read from frontend/.env for safety
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"


def _mongosh(script: str) -> str:
    out = subprocess.run(
        ["mongosh", "--quiet", "--eval", script],
        capture_output=True, text=True, timeout=20,
    )
    return out.stdout


def _seed_member():
    uid = f"user_test{int(time.time()*1000)}"
    token = f"tok_test_{uuid.uuid4().hex}"
    email = f"test.member.{uid}@example.com"
    script = f"""
use('test_database');
db.users.insertOne({{
  user_id: '{uid}', email: '{email}', name: 'Test Member',
  picture: '', is_admin: false, status: 'approved', source: 'manual_test',
  created_at: new Date().toISOString(), last_login_at: new Date().toISOString()
}});
db.user_sessions.insertOne({{
  user_id: '{uid}', session_token: '{token}',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now()+7*24*60*60*1000).toISOString()
}});
print('OK');
"""
    _mongosh(script)
    return uid, email, token


def _cleanup(uid):
    _mongosh(f"use('test_database'); db.users.deleteMany({{user_id:'{uid}'}}); db.user_sessions.deleteMany({{user_id:'{uid}'}});")


# --- Public endpoints used by new Landing page ---
class TestLandingPublicEndpoints:
    def test_posts_public(self):
        r = requests.get(f"{API}/posts/public?limit=30", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)

    def test_essays_public(self):
        r = requests.get(f"{API}/essays?limit=4", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert len(data["items"]) <= 4

    def test_prompts_current_public(self):
        r = requests.get(f"{API}/prompts/current", timeout=15)
        # Either 200 with prompt or empty dict; should not require auth
        assert r.status_code in (200, 204), r.text


# --- Auth session exchange ---
class TestAuthSession:
    def test_invalid_session_id_returns_401(self):
        r = requests.post(f"{API}/auth/session", json={"session_id": "fake-invalid-id"}, timeout=15)
        assert r.status_code in (401, 400, 502), r.text


# --- Authorization Bearer flow (bypass cookies) ---
class TestBearerAuth:
    def test_me_with_bearer_returns_user(self):
        uid, email, token = _seed_member()
        try:
            r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["user_id"] == uid
            assert data["email"] == email
            assert data["status"] == "approved"
            assert "has_profile" in data
        finally:
            _cleanup(uid)

    def test_me_without_token_401(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401, r.text

    def test_me_with_bad_bearer_401(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-token"}, timeout=15)
        assert r.status_code == 401, r.text

    def test_logout_with_bearer_clears_session(self):
        uid, _email, token = _seed_member()
        try:
            # logout
            r = requests.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert r.status_code == 200, r.text
            # token should be gone
            r2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert r2.status_code == 401, r2.text
        finally:
            _cleanup(uid)


# --- CORS sanity for credentialed requests ---
class TestCORS:
    def test_actual_get_with_bearer_works_cross_origin(self):
        """The ingress strips/rewrites CORS headers to `*`, which is why the fix is to
        use Authorization: Bearer + localStorage (not cookies). The actual GET must
        succeed cross-origin with a Bearer header even when CORS headers are `*`.
        """
        # Seed a quick session
        uid, _email, token = _seed_member()
        try:
            r = requests.get(
                f"{API}/auth/me",
                headers={
                    "Origin": "https://real-estate-social.preview.emergentagent.com",
                    "Authorization": f"Bearer {token}",
                },
                timeout=15,
            )
            assert r.status_code == 200, r.text
            assert r.json()["user_id"] == uid
        finally:
            _cleanup(uid)
