"""Integration tests for routes/broadcasts.py.

Stubs out the Resend API helpers via monkeypatch so the tests never hit
the real network. Verifies admin-gating, request/response shapes, and
that the local `brief_broadcasts` audit row is written on send.
"""
import os
import uuid

import pytest

os.environ.setdefault("RESEND_API_KEY", "test-key")


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": "x"})()

    async def find_one(self, query=None, projection=None):
        if not query:
            return self.docs[0] if self.docs else None
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None


class _FakeDb:
    def __init__(self):
        self.users = _FakeCollection()
        self.user_sessions = _FakeCollection()
        self.brief_broadcasts = _FakeCollection()


@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    db = _FakeDb()
    # Seed admin user + session row that get_current_user reads from.
    token = "tok_test_" + uuid.uuid4().hex[:8]
    user_id = "user_admin_" + uuid.uuid4().hex[:8]
    db.users.docs.append({
        "user_id": user_id,
        "email": "broadcasts.admin@example.com",
        "name": "Broadcasts Admin",
        "is_admin": True,
        "status": "approved",
    })
    db.user_sessions.docs.append({
        "session_token": token,
        "user_id": user_id,
        "email": "broadcasts.admin@example.com",
        "expires_at": "2099-01-01T00:00:00+00:00",
    })

    # Stub the Resend HTTP layer.
    fake_state = {"broadcasts": {}, "calls": []}

    def fake_create(audience_id, subject, html, from_email, from_name, reply_to=None, name=None):
        bid = "br_" + uuid.uuid4().hex[:8]
        fake_state["broadcasts"][bid] = {
            "id": bid, "audience_id": audience_id, "subject": subject,
            "html": html, "status": "draft", "from": f"{from_name} <{from_email}>",
            "name": name, "reply_to": reply_to,
        }
        fake_state["calls"].append(("create", bid))
        return {"object": "broadcast", "id": bid}

    def fake_send(bid, scheduled_at=None):
        if bid not in fake_state["broadcasts"]:
            return {"error": "not found", "status": 404}
        fake_state["broadcasts"][bid]["status"] = "queued" if scheduled_at else "sending"
        fake_state["calls"].append(("send", bid, scheduled_at))
        return {"object": "broadcast", "id": bid}

    def fake_list(limit=100):
        return list(fake_state["broadcasts"].values())

    def fake_get(bid):
        b = fake_state["broadcasts"].get(bid)
        return b or {"error": "not found", "status": 404}

    def fake_delete(bid):
        if bid in fake_state["broadcasts"]:
            del fake_state["broadcasts"][bid]
            return {"id": bid, "deleted": True}
        return {"error": "not found", "status": 404}

    def fake_patch(bid, fields):
        if bid not in fake_state["broadcasts"]:
            return {"error": "not found", "status": 404}
        fake_state["broadcasts"][bid].update(fields)
        return {"object": "broadcast", "id": bid}

    def fake_list_audiences():
        return [{"id": "aud_general", "name": "General", "totalSubscribers": None}]

    import routes.broadcasts as routes_bc
    import services.brevo_contacts as bc
    monkeypatch.setattr(routes_bc, "create_broadcast", fake_create)
    monkeypatch.setattr(routes_bc, "send_broadcast", fake_send)
    monkeypatch.setattr(routes_bc, "list_broadcasts", fake_list)
    monkeypatch.setattr(routes_bc, "get_broadcast", fake_get)
    monkeypatch.setattr(routes_bc, "delete_broadcast", fake_delete)
    monkeypatch.setattr(routes_bc, "_patch_broadcast", fake_patch)
    monkeypatch.setattr(bc, "list_brevo_lists", fake_list_audiences)
    # The route imports list_brevo_lists directly into its namespace.
    monkeypatch.setattr(routes_bc, "list_brevo_lists", fake_list_audiences)
    # Also patch the get_current_user dep to read from our in-memory db.
    import services.auth_helpers as ah
    real_get_current_user = ah.get_current_user

    async def fake_get_current_user(_db, session_token=None, authorization=None):
        tok = (authorization or "").replace("Bearer ", "") if authorization else session_token
        sess = await db.user_sessions.find_one({"session_token": tok})
        if not sess:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="not authenticated")
        user = await db.users.find_one({"user_id": sess["user_id"]})
        return user

    monkeypatch.setattr("routes.broadcasts.get_current_user", fake_get_current_user)

    app = FastAPI()
    app.include_router(routes_bc.setup(db))
    return TestClient(app), token, fake_state, db


def test_list_requires_admin(client):
    c, _, _, _ = client
    r = c.get("/api/admin/broadcasts")
    assert r.status_code in (401, 403)


def test_full_lifecycle_create_update_send_delete(client):
    c, token, state, db = client
    h = {"Authorization": f"Bearer {token}"}

    # Defaults
    r = c.get("/api/admin/broadcasts/defaults", headers=h)
    assert r.status_code == 200
    assert "from_email" in r.json()

    # Audiences
    r = c.get("/api/admin/broadcasts/audiences", headers=h)
    assert r.status_code == 200
    assert r.json()["data"][0]["id"] == "aud_general"

    # Empty list
    r = c.get("/api/admin/broadcasts", headers=h)
    assert r.status_code == 200
    assert r.json()["count"] == 0

    # Create
    r = c.post("/api/admin/broadcasts", headers=h, json={
        "audience_id": "aud_general",
        "subject": "Test broadcast",
        "html": "<p>Hello</p>",
        "name": "test",
    })
    assert r.status_code == 200, r.text
    bid = r.json()["id"]

    # Get one
    r = c.get(f"/api/admin/broadcasts/{bid}", headers=h)
    assert r.status_code == 200
    assert r.json()["subject"] == "Test broadcast"

    # Update
    r = c.patch(f"/api/admin/broadcasts/{bid}", headers=h, json={"subject": "Updated subject"})
    assert r.status_code == 200
    assert state["broadcasts"][bid]["subject"] == "Updated subject"

    # Filtered list: 1 draft
    r = c.get("/api/admin/broadcasts?status=draft", headers=h)
    assert r.json()["count"] == 1

    # Send (no schedule) → status → "sending", brief_broadcasts audit row written
    r = c.post(f"/api/admin/broadcasts/{bid}/send", headers=h, json={})
    assert r.status_code == 200, r.text
    audit_doc = next((d for d in db.brief_broadcasts.docs if d["broadcast_id"] == bid), None)
    assert audit_doc is not None
    assert audit_doc["kind"] == "manual"

    # Delete
    r = c.delete(f"/api/admin/broadcasts/{bid}", headers=h)
    assert r.status_code == 200
    assert bid not in state["broadcasts"]


def test_update_empty_payload_returns_400(client):
    c, token, _, _ = client
    h = {"Authorization": f"Bearer {token}"}
    r = c.post("/api/admin/broadcasts", headers=h, json={
        "audience_id": "aud_general", "subject": "x", "html": "<p>x</p>",
    })
    bid = r.json()["id"]
    r = c.patch(f"/api/admin/broadcasts/{bid}", headers=h, json={})
    assert r.status_code == 400
    assert "No fields to update" in r.text
