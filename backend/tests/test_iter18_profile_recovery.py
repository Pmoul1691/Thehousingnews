"""Profile-recovery path: when a member returns and their `users` row is
missing but a `profiles` row with their email still exists, /auth/session
must reuse the existing user_id so `has_profile` is true and they are NOT
sent back through onboarding.

Each test runs against a fresh TestClient/lifespan to avoid sharing the
motor event loop across tests, which causes "future belongs to a different
loop" errors when reused.
"""
import os
import time
import uuid
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
os.environ.setdefault("DB_NAME", "test_database")

import sys
sys.path.insert(0, "/app/backend")

_sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _make_client():
    from server import app
    return TestClient(app)


def _emergent_response(email: str, name: str, session_token: str):
    class _R:
        status_code = 200
        def json(self):
            return {
                "email": email,
                "name": name,
                "picture": "",
                "session_token": session_token,
            }
    return _R()


def _cleanup(email: str):
    _sync.users.delete_many({"email": email})
    _sync.profiles.delete_many({"email": email})


def test_auth_session_recovers_existing_profile_by_email():
    email = f"recovery.{int(time.time()*1000)}.{uuid.uuid4().hex[:6]}@example.com"
    legacy_uid = f"recovery_legacy_{uuid.uuid4().hex[:8]}"
    _cleanup(email)
    _sync.profiles.insert_one({
        "user_id": legacy_uid,
        "email": email,
        "name": "Legacy Profile",
        "market": "Chicago, IL",
        "bio": "old",
        "objectives": ["a", "b", "c"],
        "objectives_version": 1,
    })
    try:
        session_token = "rec_" + uuid.uuid4().hex[:12]
        with patch("routes.auth.requests.get", return_value=_emergent_response(email, "Returning Member", session_token)):
            with _make_client() as client:
                r = client.post("/api/auth/session", json={"session_id": "fake"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_id"] == legacy_uid, body
        assert body["has_profile"] is True, body
        assert body["status"] == "approved", body
        assert body["session_token"] == session_token
        user_row = _sync.users.find_one({"user_id": legacy_uid})
        assert user_row is not None
        assert user_row["source"] == "profile_recovery"
    finally:
        _cleanup(email)
        _sync.user_sessions.delete_many({"user_id": legacy_uid})


# Note: regression tests for the fresh-user and existing-user paths are
# verified against the running backend via curl; running additional TestClient
# instances in the same pytest process fails with "Event loop is closed"
# because server.py initializes a module-level Motor client whose loop tears
# down after the first lifespan exit.
