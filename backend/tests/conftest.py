"""Shared fixtures for Ultradian Network backend tests."""
import os
import subprocess
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend/.env
    env_path = "/app/frontend/.env"
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
                break


def _mongo_eval(script: str) -> str:
    """Run a mongosh eval script and return stdout."""
    result = subprocess.run(
        ["mongosh", "--quiet", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mongo failed: {result.stderr}")
    return result.stdout


def _seed_user(role: str, status: str, is_admin: bool, email: str | None = None) -> dict:
    """Seed a user + session row directly. Returns dict(user_id, token, email)."""
    ts = int(time.time() * 1000)
    user_id = f"user_{role}_{ts}"
    token = f"tok_{role}_{ts}"
    email = email or f"test.{role}.{ts}@example.com"
    script = f"""
use('test_database');
db.users.deleteMany({{email: '{email}'}});
db.users.insertOne({{
  user_id: '{user_id}',
  email: '{email}',
  name: 'Test {role.title()}',
  picture: '',
  is_admin: {str(is_admin).lower()},
  status: '{status}',
  source: 'manual_test',
  created_at: new Date().toISOString(),
  last_login_at: new Date().toISOString()
}});
db.user_sessions.insertOne({{
  user_id: '{user_id}',
  session_token: '{token}',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString()
}});
"""
    _mongo_eval(script)
    return {"user_id": user_id, "token": token, "email": email}


def _cleanup_user(user_id: str):
    script = f"""
use('test_database');
db.users.deleteMany({{user_id: '{user_id}'}});
db.user_sessions.deleteMany({{user_id: '{user_id}'}});
db.applications.deleteMany({{user_id: '{user_id}'}});
db.profiles.deleteMany({{user_id: '{user_id}'}});
db.posts.deleteMany({{user_id: '{user_id}'}});
db.replies.deleteMany({{user_id: '{user_id}'}});
db.objective_history.deleteMany({{user_id: '{user_id}'}});
"""
    try:
        _mongo_eval(script)
    except Exception:
        pass


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def bearer():
    return _bearer


@pytest.fixture
def approved_user():
    u = _seed_user("approved", "approved", False)
    yield u
    _cleanup_user(u["user_id"])


@pytest.fixture
def needs_app_user():
    u = _seed_user("needsapp", "needs_application", False)
    yield u
    _cleanup_user(u["user_id"])


@pytest.fixture
def admin_user():
    ts = int(time.time() * 1000)
    u = _seed_user("admin", "approved", True, email=f"peter@1691inc.com")
    yield u
    _cleanup_user(u["user_id"])
