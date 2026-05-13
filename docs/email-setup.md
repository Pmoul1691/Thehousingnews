# Email setup checklist — The Ultradian Network

This is the deliverability runbook for `ultradiannetwork.com`. Follow it once when launching the public domain. Re-run the test send after any DNS change.

## 1. Verify the sender in Brevo

1. Log in to Brevo.
2. Senders, Domains and IPs → **Senders** → **Add a sender**.
3. Add `peter@ultradiannetwork.com` (or whatever `BREVO_SENDER_EMAIL` is set to in `/app/backend/.env`). Confirm via the verification email Brevo sends.

## 2. Authenticate the domain

1. Same page → **Domains** → **Authenticate this domain** for `ultradiannetwork.com`.
2. Brevo will display a unique DKIM key (`mail._domainkey.ultradiannetwork.com`) and a verification token (`brevo-code=...`).
3. Add those records at your DNS host (e.g. Cloudflare, Route53). The exact records you need are listed in `/admin/email-health` inside the admin app.

## 3. DNS records summary

| Name | Type | Purpose | Value |
|---|---|---|---|
| `ultradiannetwork.com` | TXT | SPF | `v=spf1 include:spf.brevo.com ~all` |
| `mail._domainkey.ultradiannetwork.com` | TXT | DKIM | copy from Brevo |
| `_dmarc.ultradiannetwork.com` | TXT | DMARC | `v=DMARC1; p=quarantine; rua=mailto:postmaster@ultradiannetwork.com; pct=100; aspf=s; adkim=s` |
| `ultradiannetwork.com` | TXT | Brevo domain token | `brevo-code=...` |
| `www.ultradiannetwork.com` | CNAME | www → apex | `ultradiannetwork.com` |

Only one SPF TXT per domain. If you already have one for another sender, merge `include:spf.brevo.com` into it.

## 4. Validate

1. Wait 15-60 minutes for DNS to propagate.
2. Click **Validate** inside Brevo until SPF + DKIM both show green.
3. In the admin app go to `/admin/email-health` and click **Send test email**. Send it to a Gmail address.
4. Open the test in Gmail → **Show original** → confirm:
   - `SPF: PASS`
   - `DKIM: PASS`
   - `DMARC: PASS`

## 5. Tighten DMARC

Run DMARC at `p=none` for 14 days while you watch the `rua` aggregate reports. When all sources show as authorized, raise `p` to `quarantine`, and one more week later to `reject`.

## 6. Tracking pixel + link redirects

Once `APP_PUBLIC_URL` is set (e.g. `https://ultradiannetwork.com`) the digest and essay emails automatically include:

- A 1x1 open pixel at `/api/track/open/{dispatch_id}.gif`.
- Each external `<a href>` rewritten to `/api/track/click/{dispatch_id}?to=<encoded url>` which 302s to the original URL after logging a click event.

Open and click rates surface under **Admin → Analytics → Email** via `/api/admin/analytics/email`.

## 7. Common pitfalls

- **Two SPF records** at the apex → all mail fails SPF. Merge them.
- **DKIM published at the wrong selector** → Brevo uses `mail` (`mail._domainkey...`). Do not invent a different selector.
- **DMARC pointing at a non-existent mailbox** → reports never arrive. Make sure `postmaster@` is monitored.
- **APP_PUBLIC_URL missing** → tracking is silently skipped (no pixel, raw links). Set it in `/app/backend/.env` once the domain is live.
