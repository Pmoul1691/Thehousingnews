"""
Create a draft Brevo campaign — damage-control note after the signin outage.
Targets the same list as the welcome (Chicago Nurtured 0526).
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

API_KEY = os.environ["BREVO_API_KEY"]
LIST_ID = 2  # Chicago Nurtured 0526
SENDER_NAME = "Peter Moulton"
SENDER_EMAIL = "peter@thehousingnews.com"
REPLY_TO = "peter@thehousingnews.com"
SUBJECT = "A quick note about today's signin."
CAMPAIGN_NAME = "Chicago Nurtured 0526 — Signin hiccup apology"
HEADER_IMG = "https://news-lead-gen.preview.emergentagent.com/brand/email-header-thn-cream.png"
SIGNATURE_IMG = "https://news-lead-gen.preview.emergentagent.com/brand/signature-pete.png"

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<title>A quick note about today's signin</title>
<style>
  body { margin:0; padding:0; background:#F5EDD6; font-family: Georgia, 'Times New Roman', serif; color:#1a1a1a; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }
  table { border-collapse: collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }
  img { border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }
  a { color:#B8860B; text-decoration: none; }
  .wrap { width:100%; background:#F5EDD6; padding:24px 0; }
  .card { max-width:600px; margin:0 auto; background:#FFFCF2; }
  .header { background:#FFFCF2; }
  .header img { display:block; width:100%; max-width:600px; height:auto; }
  .content { padding:36px 36px 28px 36px; font-family: Georgia, 'Times New Roman', serif; font-size:17px; line-height:1.7; color:#1a1a1a; }
  .content p { margin:0 0 18px 0; }
  .btn-wrap { text-align:center; margin:28px 0; }
  .btn { display:inline-block; background:#B8860B; color:#fff !important; padding:14px 28px; font-family: Helvetica, Arial, sans-serif; font-size:15px; font-weight:600; letter-spacing:0.3px; border-radius:2px; }
  .footer { padding:24px 36px 32px 36px; font-family: Helvetica, Arial, sans-serif; font-size:12px; color:#777; line-height:1.6; border-top:1px solid #E6DDC4; }
  .footer a { color:#777; text-decoration: underline; }
  .sig { font-family: Georgia, serif; font-size:16px; color:#1a1a1a; }
  .small { font-family: Helvetica, Arial, sans-serif; font-size:13px; color:#666; }
  @media only screen and (max-width: 620px) {
    .card { width: 100% !important; max-width:100% !important; }
    .content { padding: 24px 20px 20px 20px !important; font-size:16px !important; line-height:1.65 !important; }
    .footer { padding: 20px 20px 24px 20px !important; }
    .btn { display:block !important; width: auto !important; padding: 16px 22px !important; font-size:16px !important; }
    .btn-wrap { margin: 24px 0 !important; }
    .header img { width:100% !important; height:auto !important; }
    .sig img { width: 160px !important; }
  }
</style>
</head>
<body>
  <div class="wrap">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#F5EDD6;">
      <tr><td align="center" style="padding:0;">
        <table role="presentation" class="card" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#FFFCF2;">
          <tr>
            <td class="header" style="background:#FFFCF2;">
              <a href="https://thehousingnews.com" target="_blank">
                <img src="__HEADER_IMG__" alt="The Housing News" width="600" style="display:block;width:100%;max-width:600px;height:auto;border:0;" />
              </a>
            </td>
          </tr>
          <tr>
            <td class="content">
              <p>{% if contact.FIRSTNAME %}{{ contact.FIRSTNAME }}{% else %}There{% endif %},</p>

              <p>Quick note, and an apology.</p>

              <p>So many of you tried to sign in this morning that the server couldn't keep up and crashed. A good problem to have, but not the welcome I wanted to give you. I'm sorry.</p>

              <p>We're working on it now and the site will be back up shortly. When it is, your seat is still waiting.</p>

              <div class="btn-wrap">
                <a class="btn" href="https://thehousingnews.com/subscribe" target="_blank" style="background:#B8860B;color:#ffffff;display:inline-block;padding:14px 28px;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:600;letter-spacing:0.3px;border-radius:2px;text-decoration:none;">Try again &nbsp;&rarr;</a>
              </div>

              <p>Thanks for the patience. And for showing up.</p>

              <p class="sig" style="margin-top:28px;margin-bottom:6px;">
                <img src="__SIGNATURE_IMG__" alt="Pete Moulton signature" width="180" style="display:block;width:180px;height:auto;margin:0 0 6px 0;border:0;outline:none;" />
                Peter<br/>
              <span class="small" style="color:#666;">Founder &amp; Editor, The Housing News</span></p>
            </td>
          </tr>
          <tr>
            <td class="footer">
              <a href="https://thehousingnews.com" target="_blank">thehousingnews.com</a>
              &nbsp;·&nbsp;
              <a href="{{ unsubscribe }}">Unsubscribe</a>
            </td>
          </tr>
        </table>
      </td></tr>
    </table>
  </div>
</body>
</html>
"""

html = HTML.replace("__HEADER_IMG__", HEADER_IMG).replace("__SIGNATURE_IMG__", SIGNATURE_IMG)

payload = {
    "name": CAMPAIGN_NAME,
    "subject": SUBJECT,
    "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
    "replyTo": REPLY_TO,
    "htmlContent": html,
    "recipients": {"listIds": [LIST_ID]},
    "inlineImageActivation": False,
    "mirrorActive": True,
    "footer": "The Housing News · Chicago · {{ unsubscribe }}",
    "header": "If this email does not display correctly, view it in your browser.",
}

r = requests.post(
    "https://api.brevo.com/v3/emailCampaigns",
    headers={"accept": "application/json", "content-type": "application/json", "api-key": API_KEY},
    json=payload,
    timeout=30,
)
print("CREATE status:", r.status_code)
print("body:", r.text)
