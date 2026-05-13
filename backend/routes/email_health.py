"""Admin: email health checklist (DNS records) + test send + launch readiness."""
import os
import logging
import socket
import asyncio
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from pydantic import BaseModel, EmailStr, AnyHttpUrl

from services.auth_helpers import get_current_user, is_admin_email
from services.brevo import send_email, BREVO_API_KEY, SENDER_EMAIL, SENDER_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/email", tags=["email-health"])


def _domain_from_sender() -> str:
    parts = (SENDER_EMAIL or "").split("@")
    return parts[1] if len(parts) == 2 else "ultradiannetwork.com"


def _public_domain() -> str:
    raw = os.environ.get("APP_PUBLIC_URL") or ""
    if not raw:
        return _domain_from_sender()
    try:
        host = urlparse(raw).hostname or _domain_from_sender()
        return host
    except Exception:
        return _domain_from_sender()


class TestSend(BaseModel):
    to_email: EmailStr


class PublicUrlSet(BaseModel):
    url: AnyHttpUrl


def _dns_txt(name: str) -> list[str]:
    """Best-effort TXT lookup. Returns the list of TXT values or [] on failure."""
    try:
        import dns.resolver
        ans = dns.resolver.resolve(name, "TXT", lifetime=4)
        out = []
        for r in ans:
            try:
                out.append(b"".join(r.strings).decode("utf-8", errors="ignore"))
            except Exception:
                out.append(str(r))
        return out
    except Exception:
        return []


def _http_head(url: str) -> dict:
    """Best-effort HEAD; returns {ok, status, error}."""
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"ok": 200 <= resp.status < 400, "status": resp.status}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)[:200]}


def setup(db):
    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/dns-records")
    async def dns_records(admin=Depends(_admin)):
        sender_domain = _domain_from_sender()
        public_domain = _public_domain()
        return {
            "sender_email": SENDER_EMAIL,
            "sender_domain": sender_domain,
            "public_domain": public_domain,
            "brevo_configured": bool(BREVO_API_KEY),
            "records": [
                {
                    "name": sender_domain,
                    "type": "TXT",
                    "purpose": "SPF",
                    "value": "v=spf1 include:spf.brevo.com ~all",
                    "hint": "Add this TXT record at the apex. If you already have an SPF record, merge `include:spf.brevo.com` into the existing one (only one SPF TXT per domain).",
                },
                {
                    "name": f"mail._domainkey.{sender_domain}",
                    "type": "TXT",
                    "purpose": "DKIM (Brevo)",
                    "value": "k=rsa; p=COPY_THE_PUBLIC_KEY_FROM_BREVO_SENDERS_AND_IP_PAGE",
                    "hint": "Brevo generates a unique selector per account. Go to Brevo dashboard > Senders, Domains and IPs > Domains > Authenticate this domain. Copy the `mail._domainkey` value from there.",
                },
                {
                    "name": f"_dmarc.{sender_domain}",
                    "type": "TXT",
                    "purpose": "DMARC",
                    "value": f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{sender_domain}; pct=100; aspf=s; adkim=s",
                    "hint": "Start with `p=none` for two weeks while you watch the aggregate reports, then raise to `p=quarantine` and finally `p=reject`.",
                },
                {
                    "name": public_domain,
                    "type": "TXT",
                    "purpose": "Brevo domain verification",
                    "value": "brevo-code=PASTE_FROM_BREVO_DASHBOARD",
                    "hint": "Brevo shows this token next to the DKIM key on the Authenticate Domain page.",
                },
                {
                    "name": f"www.{public_domain}",
                    "type": "CNAME",
                    "purpose": "Web hostname (optional)",
                    "value": public_domain,
                    "hint": "Point www to the apex so people who type www.ultradiannetwork.com still land on the network.",
                },
            ],
            "checklist": [
                "Verify the sender domain in Brevo > Senders, Domains and IPs.",
                "Publish the SPF, DKIM, and DMARC records above with your DNS host.",
                "Wait 15-60 minutes for propagation, then click `Validate` inside Brevo.",
                "Send a test email from this page and check the headers in Gmail with `Show original`. Look for `dkim=pass` and `spf=pass`.",
                "When everything passes, raise DMARC from `p=none` to `p=quarantine`, then `p=reject`.",
            ],
        }

    @router.post("/test-send")
    async def test_send(payload: TestSend, admin=Depends(_admin)):
        html = f"""
        <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:32px;">
          <div style="max-width:560px; margin:0 auto; background:#FDFAF4; border:1px solid #E8D4A0; padding:32px;">
            <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.12em; text-transform:uppercase; font-size:12px; margin-bottom:24px;">The Ultradian Network</div>
            <p>This is a deliverability test sent by {admin.get('email')}.</p>
            <p>If you can read this, the sender ({SENDER_EMAIL}) is configured correctly. Open the headers and look for `dkim=pass` and `spf=pass`.</p>
            <p>Pete</p>
          </div>
        </div>
        """
        result = send_email(
            to_email=payload.to_email,
            to_name="Test recipient",
            subject="Deliverability test from The Ultradian Network",
            html=html,
            tags=["ultradian_network", "deliverability_test"],
        )
        return {"sent": True, "brevo_response": result}

    @router.get("/public-url")
    async def get_public_url(admin=Depends(_admin)):
        """Returns the effective APP_PUBLIC_URL (DB override or env)."""
        row = await db.app_settings.find_one({"key": "APP_PUBLIC_URL"}, {"_id": 0})
        return {
            "value": (row or {}).get("value") or os.environ.get("APP_PUBLIC_URL", ""),
            "source": "db" if row else ("env" if os.environ.get("APP_PUBLIC_URL") else "unset"),
        }

    @router.post("/public-url")
    async def set_public_url(payload: PublicUrlSet, admin=Depends(_admin)):
        """Store the public URL in the DB so digests, tracking, and emails use it
        without needing a redeploy. The runtime accessor at services/tracking._base_url
        reads from env; this admin setter writes to BOTH env and the DB row."""
        value = str(payload.url).rstrip("/")
        await db.app_settings.update_one(
            {"key": "APP_PUBLIC_URL"},
            {"$set": {"key": "APP_PUBLIC_URL", "value": value, "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}},
            upsert=True,
        )
        # Make it effective for the rest of this process
        os.environ["APP_PUBLIC_URL"] = value
        return {"ok": True, "value": value}

    @router.get("/readiness")
    async def readiness(admin=Depends(_admin)):
        """Production launch readiness check: DNS, public URL, Brevo key."""
        sender_domain = _domain_from_sender()
        public_domain = _public_domain()
        public_url = (await get_public_url(admin)).get("value") or ""

        # Run DNS lookups in a thread so we don't block the loop
        spf, dkim, dmarc = await asyncio.gather(
            asyncio.to_thread(_dns_txt, sender_domain),
            asyncio.to_thread(_dns_txt, f"mail._domainkey.{sender_domain}"),
            asyncio.to_thread(_dns_txt, f"_dmarc.{sender_domain}"),
        )
        checks = [
            {
                "name": "SPF record",
                "ok": any("v=spf1" in v and "spf.brevo.com" in v for v in spf),
                "detail": next((v for v in spf if "v=spf1" in v), "not found"),
            },
            {
                "name": "DKIM record (mail._domainkey)",
                "ok": any("p=" in v and "k=rsa" in v for v in dkim),
                "detail": (dkim[0][:80] + "...") if dkim else "not found",
            },
            {
                "name": "DMARC record",
                "ok": any("v=DMARC1" in v for v in dmarc),
                "detail": next((v for v in dmarc if "v=DMARC1" in v), "not found"),
            },
            {
                "name": "Public URL reachable",
                "ok": False,
                "detail": "APP_PUBLIC_URL not set",
            },
            {
                "name": "Brevo API key configured",
                "ok": bool(BREVO_API_KEY),
                "detail": "configured" if BREVO_API_KEY else "BREVO_API_KEY missing",
            },
        ]
        if public_url:
            http = await asyncio.to_thread(_http_head, public_url)
            checks[3] = {
                "name": "Public URL reachable",
                "ok": http.get("ok", False),
                "detail": f"HTTP {http.get('status')}" + (f" ({http.get('error')})" if http.get("error") else ""),
            }
        ready = all(c["ok"] for c in checks)
        return {
            "ready": ready,
            "sender_domain": sender_domain,
            "public_domain": public_domain,
            "public_url": public_url,
            "checks": checks,
        }

    return router
