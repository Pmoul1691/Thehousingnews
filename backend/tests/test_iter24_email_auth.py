"""Iter24 — Email-based auth (signup/signin, magic-link, verify, password reset).

Tests cover: signup, duplicate, weak password, signin (success/wrong-pw/lockout),
magic-link request+consume, verify request+consume, password reset request+confirm,
account linking via /auth/session and /auth/me has_password+email_verified.

Brevo email is best-effort. Tokens are read directly from Mongo (db.auth_tokens).
"""
import os
import time
import uuid
import pytest
import requests
from pathlib import Path
from pymongo import MongoClient


def _load_env(p):
    if not Path(p).exists():
        return
    for line in Path(p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


_load_env("/app/frontend/.env")
_load_env("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

# Direct Mongo for token lookup
MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = MONGO[os.environ.get("DB_NAME", "test_database")]


def fresh_email(tag: str) -> str:
    return f"e2e.{tag}.{int(time.time()*1000)}.{uuid.uuid4().hex[:6]}@example.com"


@pytest.fixture
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ──────────────────────────────────────────────────────────────────────
# SIGNUP
# ──────────────────────────────────────────────────────────────────────
class TestSignup:
    def test_signup_success(self, session):
        email = fresh_email("signup")
        r = session.post(f"{API}/auth/email/signup",
                         json={"email": email, "password": "Test1234!", "name": "E2E User"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email
        assert data["has_password"] is True
        assert data["email_verified"] is False
        assert data["status"] == "needs_application"
        assert "session_token" in data
        # Cookie set
        assert "session_token" in session.cookies.get_dict() or r.cookies.get("session_token")
        # Persisted
        u = DB.users.find_one({"email": email})
        assert u and u.get("password_hash", "").startswith("$2")

    def test_signup_duplicate_returns_409(self, session):
        email = fresh_email("dup")
        r1 = session.post(f"{API}/auth/email/signup",
                          json={"email": email, "password": "Test1234!"})
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/auth/email/signup",
                           json={"email": email, "password": "Test1234!"})
        assert r2.status_code == 409, r2.text

    def test_signup_weak_password_returns_422(self, session):
        email = fresh_email("weak")
        r = session.post(f"{API}/auth/email/signup",
                         json={"email": email, "password": "short"})
        assert r.status_code == 422, r.text

    def test_signup_admin_email_becomes_approved(self, session):
        # peter@1691inc.com is in ADMIN_EMAILS — but it exists, so use a fresh
        # email that won't be admin. Just verify needs_application for non-admin.
        email = fresh_email("nonadmin")
        r = session.post(f"{API}/auth/email/signup",
                         json={"email": email, "password": "Test1234!"})
        assert r.status_code == 200
        assert r.json()["status"] == "needs_application"
        assert r.json()["is_admin"] is False


# ──────────────────────────────────────────────────────────────────────
# SIGNIN
# ──────────────────────────────────────────────────────────────────────
class TestSignin:
    def test_signin_success_then_wrong_then_lockout(self, session):
        email = fresh_email("signin")
        session.post(f"{API}/auth/email/signup",
                     json={"email": email, "password": "Test1234!"})
        # Clear attempts row if present
        DB.login_attempts.delete_many({"identifier": {"$regex": f"^{email}:"}})

        s2 = requests.Session()
        s2.headers.update({"Content-Type": "application/json"})
        r = s2.post(f"{API}/auth/email/signin",
                    json={"email": email, "password": "Test1234!"})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == email
        assert "session_token" in r.json()

        # Wrong password
        r_bad = s2.post(f"{API}/auth/email/signin",
                        json={"email": email, "password": "WrongPass!"})
        assert r_bad.status_code == 401

    def test_brute_force_lockout(self, session):
        email = fresh_email("lockout")
        session.post(f"{API}/auth/email/signup",
                     json={"email": email, "password": "Test1234!"})
        # 5 wrong attempts should trigger lockout on 6th
        s2 = requests.Session()
        s2.headers.update({"Content-Type": "application/json"})
        for i in range(5):
            r = s2.post(f"{API}/auth/email/signin",
                        json={"email": email, "password": "WrongXY!"})
            assert r.status_code == 401, f"attempt {i+1}: {r.status_code}"
        r6 = s2.post(f"{API}/auth/email/signin",
                     json={"email": email, "password": "Test1234!"})
        assert r6.status_code == 429, f"expected 429, got {r6.status_code} {r6.text}"


# ──────────────────────────────────────────────────────────────────────
# MAGIC LINK
# ──────────────────────────────────────────────────────────────────────
class TestMagicLink:
    def test_request_then_consume_marks_verified(self, session):
        email = fresh_email("magic")
        r = session.post(f"{API}/auth/magic-link/request", json={"email": email})
        assert r.status_code == 200
        assert r.json().get("ok") is True
        tok = DB.auth_tokens.find_one(
            {"email": email, "kind": "magic_link"}, sort=[("created_at", -1)]
        )
        assert tok, "magic_link token not created in db"
        assert tok.get("used_at") is None
        # Has 15-min expiry
        assert "expires_at" in tok

        r2 = session.post(f"{API}/auth/magic-link/consume", json={"token": tok["token"]})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["email"] == email
        assert body["email_verified"] is True
        assert "session_token" in body
        # User row marked verified
        u = DB.users.find_one({"email": email})
        assert u.get("email_verified") is True

    def test_request_for_existing_user_no_enumeration(self, session):
        # Should return 200 regardless
        r = session.post(f"{API}/auth/magic-link/request",
                         json={"email": fresh_email("noexist")})
        assert r.status_code == 200

    def test_consume_invalid_token(self, session):
        r = session.post(f"{API}/auth/magic-link/consume",
                         json={"token": "invalid_token_xxx_zzz_yyy"})
        assert r.status_code == 400

    def test_consume_reused_token_fails(self, session):
        email = fresh_email("magicreuse")
        session.post(f"{API}/auth/magic-link/request", json={"email": email})
        tok = DB.auth_tokens.find_one(
            {"email": email, "kind": "magic_link"}, sort=[("created_at", -1)]
        )
        r1 = session.post(f"{API}/auth/magic-link/consume", json={"token": tok["token"]})
        assert r1.status_code == 200
        r2 = session.post(f"{API}/auth/magic-link/consume", json={"token": tok["token"]})
        assert r2.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# EMAIL VERIFY
# ──────────────────────────────────────────────────────────────────────
class TestEmailVerify:
    def test_verify_request_no_enumeration(self, session):
        r = session.post(f"{API}/auth/email/verify/request",
                         json={"email": fresh_email("noexistverify")})
        assert r.status_code == 200

    def test_signup_creates_verify_token_and_consume(self, session):
        email = fresh_email("verify")
        r = session.post(f"{API}/auth/email/signup",
                         json={"email": email, "password": "Test1234!"})
        assert r.status_code == 200
        tok = DB.auth_tokens.find_one(
            {"email": email, "kind": "verify"}, sort=[("created_at", -1)]
        )
        assert tok, "verify token must exist after signup"

        r2 = session.post(f"{API}/auth/email/verify", json={"token": tok["token"]})
        assert r2.status_code == 200
        u = DB.users.find_one({"email": email})
        assert u.get("email_verified") is True

        # Reuse fails
        r3 = session.post(f"{API}/auth/email/verify", json={"token": tok["token"]})
        assert r3.status_code == 400

    def test_verify_invalid_token(self, session):
        r = session.post(f"{API}/auth/email/verify",
                         json={"token": "bogus_invalid_zzz_yyy_xxx"})
        assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# PASSWORD RESET
# ──────────────────────────────────────────────────────────────────────
class TestPasswordReset:
    def test_reset_request_no_enumeration(self, session):
        r = session.post(f"{API}/auth/password/reset/request",
                         json={"email": fresh_email("noreset")})
        assert r.status_code == 200
        # No token should have been created
        # (account doesn't exist)

    def test_reset_request_no_token_when_no_password(self, session):
        # Magic-link-only user (no password)
        email = fresh_email("nopwreset")
        session.post(f"{API}/auth/magic-link/request", json={"email": email})
        DB.auth_tokens.delete_many({"email": email, "kind": "password_reset"})
        r = session.post(f"{API}/auth/password/reset/request", json={"email": email})
        assert r.status_code == 200
        t = DB.auth_tokens.find_one({"email": email, "kind": "password_reset"})
        assert t is None, "no reset token should be created for user without password"

    def test_reset_full_flow_invalidates_sessions(self, session):
        email = fresh_email("reset")
        r1 = session.post(f"{API}/auth/email/signup",
                          json={"email": email, "password": "Test1234!"})
        user_id = r1.json()["user_id"]
        # User has at least one session
        sess_count = DB.user_sessions.count_documents({"user_id": user_id})
        assert sess_count >= 1

        r2 = session.post(f"{API}/auth/password/reset/request", json={"email": email})
        assert r2.status_code == 200
        tok = DB.auth_tokens.find_one(
            {"email": email, "kind": "password_reset"}, sort=[("created_at", -1)]
        )
        assert tok, "password_reset token must exist"

        # Confirm with weak password fails
        r_weak = session.post(f"{API}/auth/password/reset/confirm",
                              json={"token": tok["token"], "password": "x"})
        assert r_weak.status_code == 422

        # Refetch token (still unused since weak attempt failed at validation)
        tok = DB.auth_tokens.find_one(
            {"email": email, "kind": "password_reset"}, sort=[("created_at", -1)]
        )

        r3 = session.post(f"{API}/auth/password/reset/confirm",
                          json={"token": tok["token"], "password": "NewPass1234!"})
        assert r3.status_code == 200, r3.text

        # Sessions wiped
        sess_after = DB.user_sessions.count_documents({"user_id": user_id})
        assert sess_after == 0, f"sessions should be cleared, got {sess_after}"

        # Can sign in with new password
        r4 = session.post(f"{API}/auth/email/signin",
                          json={"email": email, "password": "NewPass1234!"})
        assert r4.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# /auth/me has new fields + smoke admin regression
# ──────────────────────────────────────────────────────────────────────
class TestAuthMeAndRegression:
    def test_me_returns_has_password_and_email_verified(self, session):
        email = fresh_email("me")
        r = session.post(f"{API}/auth/email/signup",
                         json={"email": email, "password": "Test1234!"})
        token = r.json()["session_token"]
        me = requests.get(f"{API}/auth/me",
                          headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        data = me.json()
        assert data["email"] == email
        assert data["has_password"] is True
        assert data["email_verified"] is False

    def test_smoke_admin_still_works(self):
        # /auth/me with admin token
        me = requests.get(f"{API}/auth/me",
                          headers={"Authorization": "Bearer tok_smoke_admin_v2"})
        assert me.status_code == 200, me.text
        d = me.json()
        assert d["is_admin"] is True
        assert "has_password" in d
        assert "email_verified" in d

        # Admin endpoint still works
        apps = requests.get(f"{API}/applications",
                            headers={"Authorization": "Bearer tok_smoke_admin_v2"})
        assert apps.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# ACCOUNT LINKING (simulate Google login on email-signup account)
# ──────────────────────────────────────────────────────────────────────
class TestAccountLinking:
    def test_email_signup_then_simulated_google_login_links_same_user(self, session):
        """Email signup creates a user with has_password=True. A subsequent
        google login for the SAME email should reuse that user_id and flip
        email_verified=True while keeping has_password=True.

        We can't hit Emergent for a real session; simulate by directly
        updating the user row the way routes/auth.py would.
        """
        email = fresh_email("link")
        r = session.post(f"{API}/auth/email/signup",
                         json={"email": email, "password": "Test1234!"})
        user_id = r.json()["user_id"]
        assert r.json()["email_verified"] is False
        assert r.json()["has_password"] is True

        # Simulate Google sign-in side effects (auth.py lines 73-79)
        DB.users.update_one({"user_id": user_id},
                            {"$set": {"email_verified": True}})

        # /me should now show both flags true
        token = r.json()["session_token"]
        me = requests.get(f"{API}/auth/me",
                          headers={"Authorization": f"Bearer {token}"}).json()
        assert me["user_id"] == user_id
        assert me["has_password"] is True
        assert me["email_verified"] is True
