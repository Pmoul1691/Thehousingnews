# Public domain launch checklist — The Ultradian Network

A one-page runbook for going live on `ultradiannetwork.com`. Work top to bottom. Nothing in code needs to change to launch; this is mostly DNS + a flip of `APP_PUBLIC_URL`.

## 1. DNS records

Add at your registrar (Cloudflare, Route53, etc.). Wait 15-60 minutes for propagation between steps.

| Name | Type | Value | Purpose |
|---|---|---|---|
| `ultradiannetwork.com` | A or ALIAS | (your deployment IP / hostname) | Apex → app |
| `www.ultradiannetwork.com` | CNAME | `ultradiannetwork.com` | www → apex |
| `ultradiannetwork.com` | TXT | `v=spf1 include:spf.brevo.com ~all` | SPF |
| `mail._domainkey.ultradiannetwork.com` | TXT | copy from Brevo | DKIM |
| `_dmarc.ultradiannetwork.com` | TXT | `v=DMARC1; p=none; rua=mailto:postmaster@ultradiannetwork.com` | DMARC (start at p=none) |

The exact `mail._domainkey` value lives in Brevo → Senders, Domains and IPs → Authenticate this domain.

## 2. Flip the public URL

Once DNS resolves, set the public URL inside the app. Two ways:

**From the admin UI**: visit `/admin/email-health` → "Public URL" card → paste `https://ultradiannetwork.com` → Save. Takes effect immediately; no redeploy.

**Or via env** (`/app/backend/.env`):
```
APP_PUBLIC_URL=https://ultradiannetwork.com
```

If both are set, the DB value wins. Tracking pixel + click-redirect URLs in digest and essay emails will now resolve to the public domain.

## 3. Readiness check

Visit `/admin/email-health` and click "Run readiness check". Every row must be green:

- SPF record
- DKIM record
- DMARC record
- Public URL reachable
- Brevo API key configured

If any row is red, follow the detail to fix.

## 4. Send a test email

On the same page, send a test to a Gmail address you own. Open the email → "Show original". Confirm:

- `SPF: PASS`
- `DKIM: PASS`
- `DMARC: PASS`

## 5. Tighten DMARC over two weeks

Start DMARC at `p=none` for 14 days while you watch the `rua` aggregate reports. When all sources show as authorized, raise:

- Day 14: `p=quarantine`
- Day 28: `p=reject`

## 6. SEO basics (already shipped)

The app ships with the following static files. Verify they resolve once the domain is live.

- `/robots.txt` — allows everything except `/api/*`
- `/sitemap.xml` — generated daily by a cron worker; manually trigger with `POST /api/admin/sitemap/regenerate`
- Open Graph + Twitter Card meta tags in `/app/frontend/public/index.html` so links to your domain preview with the network mark
- Favicon (`/favicon.ico`)

The OG image is `og-image.png` at the public root. Replace it with a 1200x630 PNG if you want a custom share card.

## 7. Common gotchas

- **Two SPF records at the apex** = all mail fails SPF. Merge into one.
- **DKIM at the wrong selector**. Brevo uses `mail._domainkey...`. Do not invent a different selector.
- **APP_PUBLIC_URL has a trailing slash**. The admin setter strips it, but if you edit `.env` directly, leave it off.
- **CORS preflight failing in production**. The backend currently uses `allow_origins=["*"]`. If you tighten this for production, allowlist `https://ultradiannetwork.com` and `https://www.ultradiannetwork.com`.
