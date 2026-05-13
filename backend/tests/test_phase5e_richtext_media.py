"""Phase 5e: Backend coverage for inline media (video/audio/iframe) in markdown render + essay HTML."""
import os
import subprocess
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
                break


def _bearer(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mongo(script: str) -> str:
    r = subprocess.run(["mongosh", "--quiet", "--eval", script], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout


# section: services/markdown_render.py allowlist now permits iframe/video/audio/source
class TestMarkdownRenderInlineMedia:
    def test_iframe_preserved(self):
        from services.markdown_render import render
        out = render('hello\n\n<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" width="640" height="360" allowfullscreen></iframe>')
        assert "<iframe" in out
        assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in out
        assert "allowfullscreen" in out

    def test_video_preserved(self):
        from services.markdown_render import render
        out = render('<video controls preload="metadata" src="https://example.com/v.mp4"></video>')
        assert "<video" in out
        assert 'src="https://example.com/v.mp4"' in out
        assert "controls" in out

    def test_audio_preserved(self):
        from services.markdown_render import render
        out = render('<audio controls src="https://example.com/a.mp3"></audio>')
        assert "<audio" in out
        assert 'src="https://example.com/a.mp3"' in out

    def test_source_inside_video(self):
        from services.markdown_render import render
        out = render('<video controls><source src="https://example.com/v.mp4" type="video/mp4"></video>')
        assert "<source" in out
        assert 'type="video/mp4"' in out

    def test_script_still_stripped(self):
        from services.markdown_render import render
        out = render('<iframe src="x"></iframe><script>alert(1)</script>')
        assert "<iframe" in out
        assert "<script" not in out


# section: GET /api/essays/{id} body.text + body.html with inline iframe
class TestEssayInlineIframe:
    def test_essay_with_inline_iframe_round_trips(self, approved_user):
        body = (
            "# Hello\n\nThis essay has inline media.\n\n"
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" width="640" height="360" allowfullscreen></iframe>\n\n'
            + ("filler text " * 30)
        )
        r = requests.post(
            f"{BASE_URL}/api/posts",
            headers=_bearer(approved_user["token"]),
            json={"kind": "essay", "title": "InlineIframe", "text": body},
        )
        assert r.status_code == 200, r.text
        pid = r.json()["post_id"]
        try:
            g = requests.get(f"{BASE_URL}/api/essays/{pid}", headers=_bearer(approved_user["token"]))
            assert g.status_code == 200
            data = g.json()
            assert data["paywall"] is False
            assert "<iframe" in data["text"]
            assert "<iframe" in data["html"]
            assert "youtube.com/embed/dQw4w9WgXcQ" in data["html"]
        finally:
            _mongo(f"use('test_database'); db.posts.deleteMany({{post_id:'{pid}'}});")
