"""Phase 4b: Email health (DNS records / test-send), Member invites, Email tracking, Analytics."""
import os
import time
import uuid
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
                break


def _mongo(script):
    r = subprocess.run(["mongosh", "--quiet", "--eval", script],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- Email health (admin) ---
class TestEmailHealth:
    def test_dns_records_admin(self, admin_user):
        r = requests.get(f"{BASE_URL}/api/admin/email/dns-records", headers=_hdr(admin_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "sender_email" in data
        assert "sender_domain" in data
        assert "public_domain" in data
        assert "brevo_configured" in data
        assert isinstance(data["records"], list) and len(data["records"]) == 5
        for rec in data["records"]:
            assert {"name", "type", "purpose", "value", "hint"}.issubset(rec.keys())
        assert isinstance(data["checklist"], list) and len(data["checklist"]) >= 4

    def test_dns_records_non_admin_forbidden(self, approved_user):
        r = requests.get(f"{BASE_URL}/api/admin/email/dns-records", headers=_hdr(approved_user["token"]))
        assert r.status_code == 403

    def test_test_send_invalid_email_422(self, admin_user):
        r = requests.post(f"{BASE_URL}/api/admin/email/test-send",
                          headers=_hdr(admin_user["token"]),
                          json={"to_email": "not-an-email"})
        assert r.status_code == 422

    def test_test_send_non_admin_forbidden(self, approved_user):
        r = requests.post(f"{BASE_URL}/api/admin/email/test-send",
                          headers=_hdr(approved_user["token"]),
                          json={"to_email": "x@example.com"})
        assert r.status_code == 403


# --- Member invites ---
class TestInvites:
    def test_list_requires_approved(self, needs_app_user):
        r = requests.get(f"{BASE_URL}/api/me/invites", headers=_hdr(needs_app_user["token"]))
        assert r.status_code == 403

    def test_list_approved_empty(self, approved_user):
        r = requests.get(f"{BASE_URL}/api/me/invites", headers=_hdr(approved_user["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["max_per_quarter"] == 2
        assert d["issued"] == 0
        assert d["remaining"] == 2
        assert isinstance(d["items"], list)

    def test_generate_two_then_third_rejected(self, approved_user):
        h = _hdr(approved_user["token"])
        r1 = requests.post(f"{BASE_URL}/api/me/invites", headers=h)
        assert r1.status_code == 200, r1.text
        c1 = r1.json()["code"]
        assert len(c1) == 8
        r2 = requests.post(f"{BASE_URL}/api/me/invites", headers=h)
        assert r2.status_code == 200, r2.text
        c2 = r2.json()["code"]
        assert c2 != c1
        r3 = requests.post(f"{BASE_URL}/api/me/invites", headers=h)
        assert r3.status_code == 400
        assert "2 invites" in r3.json().get("detail", "")
        # Verify list reflects 2 issued, 0 redeemed
        lst = requests.get(f"{BASE_URL}/api/me/invites", headers=h).json()
        assert lst["issued"] == 2
        assert lst["redeemed"] == 0
        assert lst["remaining"] == 0

    def test_revoke_unused_code(self, approved_user):
        h = _hdr(approved_user["token"])
        gen = requests.post(f"{BASE_URL}/api/me/invites", headers=h).json()
        code = gen["code"]
        d = requests.delete(f"{BASE_URL}/api/me/invites/{code}", headers=h)
        assert d.status_code == 200, d.text
        # Generating again should work since count back to 0
        r2 = requests.post(f"{BASE_URL}/api/me/invites", headers=h)
        assert r2.status_code == 200

    def test_revoke_redeemed_rejected(self, approved_user, needs_app_user):
        h = _hdr(approved_user["token"])
        gen = requests.post(f"{BASE_URL}/api/me/invites", headers=h).json()
        code = gen["code"]
        # Use it via application
        app_payload = {
            "why_joining": "I want to learn from peers and share insights " * 2,
            "current_role": "Broker",
            "market": "NYC",
            "years_in_real_estate": "5",
            "invite_code": code,
        }
        r = requests.post(f"{BASE_URL}/api/applications",
                          headers=_hdr(needs_app_user["token"]),
                          json=app_payload)
        assert r.status_code == 200, r.text
        # Now revoke must fail
        d = requests.delete(f"{BASE_URL}/api/me/invites/{code}", headers=h)
        assert d.status_code == 400

    def test_public_validate(self, approved_user):
        h = _hdr(approved_user["token"])
        gen = requests.post(f"{BASE_URL}/api/me/invites", headers=h).json()
        code = gen["code"]
        # public validate (no auth header)
        v = requests.post(f"{BASE_URL}/api/invite/validate", json={"code": code})
        assert v.status_code == 200, v.text
        body = v.json()
        assert body["ok"] is True
        assert body.get("owner_name")
        # Unknown code => 404
        v2 = requests.post(f"{BASE_URL}/api/invite/validate", json={"code": "ZZZZZZZZ"})
        assert v2.status_code == 404

    def test_application_redeems_and_marks(self, approved_user, needs_app_user):
        h = _hdr(approved_user["token"])
        gen = requests.post(f"{BASE_URL}/api/me/invites", headers=h).json()
        code = gen["code"]
        app_payload = {
            "why_joining": "Looking to connect with experienced operators in the network for insights",
            "current_role": "Investor",
            "market": "Austin",
            "years_in_real_estate": "8",
            "invite_code": code,
        }
        r = requests.post(f"{BASE_URL}/api/applications",
                          headers=_hdr(needs_app_user["token"]), json=app_payload)
        assert r.status_code == 200, r.text
        app_id = r.json()["application_id"]
        # validate now must reject as already used
        v = requests.post(f"{BASE_URL}/api/invite/validate", json={"code": code})
        assert v.status_code == 400
        # Direct mongo check: application has invited_by_user_id / invited_by_name
        out = _mongo(f"use('test_database'); var a = db.applications.findOne({{application_id: '{app_id}'}}); print(a.invited_by_name + '|' + a.invited_by_user_id);")
        assert approved_user["user_id"] in out
        # Re-use the same code (different applicant) -> 400
        # Reset the second user's status so application doesn't short-circuit
        _mongo(f"use('test_database'); db.users.updateOne({{user_id: '{needs_app_user['user_id']}'}}, {{$set: {{status: 'needs_application'}}}}); db.applications.deleteMany({{user_id: '{needs_app_user['user_id']}'}});")
        r2 = requests.post(f"{BASE_URL}/api/applications",
                           headers=_hdr(needs_app_user["token"]), json=app_payload)
        assert r2.status_code == 400


# --- Tracking ---
class TestTracking:
    def test_open_pixel_inserts_event(self):
        dispatch_id = f"disp_test_{uuid.uuid4().hex[:8]}"
        r = requests.get(f"{BASE_URL}/api/track/open/{dispatch_id}.gif")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/gif")
        assert len(r.content) > 10
        # Verify event row inserted
        out = _mongo(f"use('test_database'); print(db.email_events.countDocuments({{dispatch_id: '{dispatch_id}', kind: 'open'}}));")
        assert "1" in out.strip().splitlines()[-1]

    def test_click_redirects_302(self):
        dispatch_id = f"disp_test_{uuid.uuid4().hex[:8]}"
        target = "https://example.com/foo"
        r = requests.get(f"{BASE_URL}/api/track/click/{dispatch_id}",
                         params={"to": target}, allow_redirects=False)
        assert r.status_code == 302
        assert r.headers.get("location") == target
        out = _mongo(f"use('test_database'); print(db.email_events.countDocuments({{dispatch_id: '{dispatch_id}', kind: 'click'}}));")
        assert "1" in out.strip().splitlines()[-1]

    def test_click_rejects_empty_target(self):
        dispatch_id = f"disp_test_{uuid.uuid4().hex[:8]}"
        r = requests.get(f"{BASE_URL}/api/track/click/{dispatch_id}",
                         params={"to": ""}, allow_redirects=False)
        assert r.status_code == 400

    def test_click_rejects_non_http(self):
        dispatch_id = f"disp_test_{uuid.uuid4().hex[:8]}"
        r = requests.get(f"{BASE_URL}/api/track/click/{dispatch_id}",
                         params={"to": "javascript:alert(1)"}, allow_redirects=False)
        assert r.status_code == 400

    def test_wrap_for_tracking_helper(self):
        # Set APP_PUBLIC_URL in this process (backend/.env is read by backend, not pytest).
        os.environ["APP_PUBLIC_URL"] = "https://agg-reader-first.preview.emergentagent.com"
        import sys
        sys.path.insert(0, "/app/backend")
        # Force reload so _base_url picks up env var
        if "services.tracking" in sys.modules:
            del sys.modules["services.tracking"]
        from importlib import import_module
        mod = import_module("services.tracking")
        html = '<html><body><p>Hello</p><a href="https://x.com/path">link</a><a href="mailto:a@b.com">mail</a></body></html>'
        out = mod.wrap_for_tracking(html, "disp_abc123")
        assert "/api/track/click/disp_abc123" in out
        assert "to=https%3A%2F%2Fx.com%2Fpath" in out
        assert "mailto:a@b.com" in out  # untouched
        assert "/api/track/open/disp_abc123.gif" in out


# --- Email analytics ---
class TestEmailAnalytics:
    def test_email_analytics_admin(self, admin_user):
        # Seed a couple of dispatches + matching events
        ts = int(time.time())
        d1 = f"disp_anal_{ts}_a"
        d2 = f"disp_anal_{ts}_b"
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        script = f"""
use('test_database');
db.email_dispatches.insertMany([
  {{dispatch_id: '{d1}', kind: 'digest', window_label: 'AM-{ts}', post_id: null, created_at: '{now}', first_opened_at: '{now}', first_clicked_at: null}},
  {{dispatch_id: '{d2}', kind: 'essay', window_label: null, post_id: 'post_{ts}', created_at: '{now}', first_opened_at: '{now}', first_clicked_at: '{now}'}}
]);
"""
        _mongo(script)
        r = requests.get(f"{BASE_URL}/api/admin/analytics/email", headers=_hdr(admin_user["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "totals" in d and "items" in d
        for k in ("sent", "opened", "clicked", "open_rate", "click_rate"):
            assert k in d["totals"]
        # cleanup
        _mongo(f"use('test_database'); db.email_dispatches.deleteMany({{dispatch_id: {{$in: ['{d1}','{d2}']}}}});")

    def test_email_analytics_non_admin_forbidden(self, approved_user):
        r = requests.get(f"{BASE_URL}/api/admin/analytics/email", headers=_hdr(approved_user["token"]))
        assert r.status_code == 403
