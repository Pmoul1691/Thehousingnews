"""Phase 7 tests: HLS hybrid pipeline + Public URL setter + Launch readiness."""
import os
import subprocess
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

VIDEO_75S = "/tmp/phase7_75s.mp4"
VIDEO_200S = "/tmp/phase7_200s.mp4"
VIDEO_5S = "/tmp/phase7_5s.mp4"


def _ensure_fixtures():
    if not os.path.exists(VIDEO_75S):
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=duration=75:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=75",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-shortest", VIDEO_75S, "-loglevel", "error",
        ], check=True)
    if not os.path.exists(VIDEO_200S):
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=duration=200:size=320x240:rate=10",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            VIDEO_200S, "-loglevel", "error",
        ], check=True)
    if not os.path.exists(VIDEO_5S):
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=duration=5:size=320x240:rate=15",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            VIDEO_5S, "-loglevel", "error",
        ], check=True)


def _seed_user(is_admin=False, email=None):
    suffix = str(int(time.time() * 1000))
    uid = f"user_p7_{suffix}"
    tok = f"tok_p7_{suffix}"
    em = email or (f"peter@1691inc.com" if is_admin else f"p7.{suffix}@example.com")
    # delete + reinsert to avoid email_1 dup key on admin reseed
    script = f"""
use('test_database');
db.users.deleteMany({{email: '{em}'}});
db.users.insertOne({{
  user_id: '{uid}', email: '{em}', name: 'P7', picture: '',
  is_admin: {str(is_admin).lower()}, status: 'approved', source: 'manual_test',
  created_at: new Date().toISOString(), last_login_at: new Date().toISOString()
}});
db.user_sessions.insertOne({{
  user_id: '{uid}', session_token: '{tok}',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString()
}});
"""
    subprocess.run(["mongosh", "--quiet", "--eval", script], check=True, capture_output=True)
    return tok, uid, em


@pytest.fixture(scope="module", autouse=True)
def fixtures():
    _ensure_fixtures()
    yield


@pytest.fixture(scope="module")
def member():
    tok, uid, em = _seed_user(is_admin=False)
    yield {"token": tok, "user_id": uid, "email": em, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def member2():
    tok, uid, em = _seed_user(is_admin=False)
    yield {"token": tok, "user_id": uid, "email": em, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def admin():
    tok, uid, em = _seed_user(is_admin=True)
    yield {"token": tok, "user_id": uid, "email": em, "headers": {"Authorization": f"Bearer {tok}"}}


# ---------------- HLS hybrid pipeline ----------------

class TestHLSHybrid:
    def test_short_video_still_inline(self, member):
        with open(VIDEO_5S, "rb") as f:
            data = f.read()
        r = requests.post(f"{BASE_URL}/api/uploads", headers=member["headers"],
                          files={"file": ("v5.mp4", data, "video/mp4")})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("media_kind") == "video"
        assert b.get("path"), "short video must return synchronous path"
        assert "processing" not in b
        assert b.get("duration_s", 0) > 0
        assert b.get("thumbnail_path")

    def test_long_video_queues_transcode(self, member):
        with open(VIDEO_75S, "rb") as f:
            data = f.read()
        r = requests.post(f"{BASE_URL}/api/uploads", headers=member["headers"],
                          files={"file": ("v75.mp4", data, "video/mp4")})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("processing") is True
        assert b.get("transcode_job_id")
        assert "path" not in b
        assert 70 < b.get("duration_s", 0) < 80
        assert b.get("width", 0) > 0 and b.get("height", 0) > 0

        # Poll until ready
        job_id = b["transcode_job_id"]
        hls_path = None
        for _ in range(60):
            s = requests.get(f"{BASE_URL}/api/uploads/transcode/{job_id}", headers=member["headers"])
            assert s.status_code == 200
            row = s.json()
            assert row["status"] in ("queued", "processing", "ready", "failed")
            if row["status"] == "ready":
                hls_path = row["hls_path"]
                break
            if row["status"] == "failed":
                pytest.fail(f"transcode failed: {row.get('error')}")
            time.sleep(2)
        assert hls_path, "transcode did not reach ready in time"
        assert hls_path.endswith("master.m3u8")

        # Fetch the playlist
        pr = requests.get(f"{BASE_URL}/api/uploads/file/{hls_path}")
        assert pr.status_code == 200
        assert "application/vnd.apple.mpegurl" in pr.headers.get("content-type", "").lower()
        body = pr.text
        assert body.startswith("#EXTM3U"), body[:80]
        # First segment referenced
        seg_lines = [ln.strip() for ln in body.splitlines() if ln.strip().endswith(".ts")]
        assert seg_lines, "no .ts segments referenced"
        seg_path = hls_path.rsplit("/", 1)[0] + "/" + seg_lines[0]
        sr = requests.get(f"{BASE_URL}/api/uploads/file/{seg_path}")
        assert sr.status_code == 200
        assert "video/mp2t" in sr.headers.get("content-type", "").lower()

        # Save for posts test
        TestHLSHybrid._hls_path = hls_path

    def test_transcode_404_for_unknown(self, member):
        r = requests.get(f"{BASE_URL}/api/uploads/transcode/nope_nope_nope", headers=member["headers"])
        assert r.status_code == 404

    def test_transcode_403_for_other_user(self, member, member2):
        # member uploads a long video, member2 tries to read the job
        with open(VIDEO_75S, "rb") as f:
            data = f.read()
        r = requests.post(f"{BASE_URL}/api/uploads", headers=member["headers"],
                          files={"file": ("v75b.mp4", data, "video/mp4")})
        assert r.status_code == 200
        jid = r.json()["transcode_job_id"]
        s = requests.get(f"{BASE_URL}/api/uploads/transcode/{jid}", headers=member2["headers"])
        assert s.status_code == 403, s.text

    def test_too_long_video_rejected(self, member):
        with open(VIDEO_200S, "rb") as f:
            data = f.read()
        r = requests.post(f"{BASE_URL}/api/uploads", headers=member["headers"],
                          files={"file": ("v200.mp4", data, "video/mp4")})
        assert r.status_code == 400, r.text
        assert "180" in r.text or "shorter" in r.text.lower()

    def test_oversized_video_rejected(self, member):
        big = b"\x00" * (205 * 1024 * 1024)
        r = requests.post(f"{BASE_URL}/api/uploads", headers=member["headers"],
                          files={"file": ("huge.mp4", big, "video/mp4")})
        assert r.status_code == 413, r.text


# ---------------- Posts accept hls_path ----------------

class TestPostsHLS:
    def test_post_with_hls_only(self, member):
        # First produce an HLS asset
        with open(VIDEO_75S, "rb") as f:
            data = f.read()
        r = requests.post(f"{BASE_URL}/api/uploads", headers=member["headers"],
                          files={"file": ("v75c.mp4", data, "video/mp4")})
        assert r.status_code == 200
        jid = r.json()["transcode_job_id"]
        hls_path = None
        for _ in range(60):
            s = requests.get(f"{BASE_URL}/api/uploads/transcode/{jid}", headers=member["headers"])
            row = s.json()
            if row.get("status") == "ready":
                hls_path = row["hls_path"]; break
            if row.get("status") == "failed":
                pytest.fail(f"transcode failed: {row.get('error')}")
            time.sleep(2)
        assert hls_path

        payload = {
            "kind": "post",
            "text": "HLS test post",
            "media": [{"kind": "video", "hls_path": hls_path}],
        }
        r = requests.post(f"{BASE_URL}/api/posts", headers=member["headers"], json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["post_id"]
        # Confirm persisted
        mine = requests.get(f"{BASE_URL}/api/posts/mine", headers=member["headers"])
        post = next((p for p in mine.json()["items"] if p["post_id"] == pid), None)
        assert post
        assert post["media"][0]["kind"] == "video"
        assert post["media"][0].get("hls_path") == hls_path

    def test_video_media_without_path_or_hls_rejected(self, member):
        payload = {"kind": "post", "text": "x", "media": [{"kind": "video"}]}
        r = requests.post(f"{BASE_URL}/api/posts", headers=member["headers"], json=payload)
        assert r.status_code == 422


# ---------------- Public URL setter + readiness ----------------

class TestPublicUrl:
    def test_get_public_url_requires_admin(self, member):
        r = requests.get(f"{BASE_URL}/api/admin/email/public-url", headers=member["headers"])
        assert r.status_code == 403

    def test_set_public_url_requires_admin(self, member):
        r = requests.post(f"{BASE_URL}/api/admin/email/public-url", headers=member["headers"],
                          json={"url": "https://evil.example.com"})
        assert r.status_code == 403

    def test_readiness_requires_admin(self, member):
        r = requests.get(f"{BASE_URL}/api/admin/email/readiness", headers=member["headers"])
        assert r.status_code == 403

    def test_get_public_url_as_admin(self, admin):
        r = requests.get(f"{BASE_URL}/api/admin/email/public-url", headers=admin["headers"])
        assert r.status_code == 200, r.text
        b = r.json()
        assert "value" in b
        assert b.get("source") in ("env", "db", "unset")

    def test_set_then_get_public_url(self, admin):
        # Use a known reachable URL
        test_url = "https://example.com"
        try:
            r = requests.post(f"{BASE_URL}/api/admin/email/public-url",
                              headers=admin["headers"], json={"url": test_url})
            assert r.status_code == 200, r.text
            assert r.json().get("value") == test_url

            g = requests.get(f"{BASE_URL}/api/admin/email/public-url", headers=admin["headers"])
            assert g.status_code == 200
            assert g.json().get("value") == test_url
            assert g.json().get("source") == "db"

            # Readiness should now include 5 checks
            rd = requests.get(f"{BASE_URL}/api/admin/email/readiness", headers=admin["headers"])
            assert rd.status_code == 200, rd.text
            data = rd.json()
            assert "checks" in data and len(data["checks"]) == 5
            names = [c["name"] for c in data["checks"]]
            assert any("SPF" in n for n in names)
            assert any("DKIM" in n for n in names)
            assert any("DMARC" in n for n in names)
            assert any("Public URL" in n for n in names)
            assert any("Brevo" in n for n in names)
            for c in data["checks"]:
                assert "ok" in c and isinstance(c["ok"], bool)
        finally:
            # Reset DB row + env so subsequent runs don't see stale value
            subprocess.run(["mongosh", "--quiet", "--eval",
                            "use('test_database'); db.app_settings.deleteMany({key:'APP_PUBLIC_URL'});"],
                           check=False, capture_output=True)
