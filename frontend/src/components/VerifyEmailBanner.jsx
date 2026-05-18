import React, { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

/**
 * Mapping from common consumer email domains to a webmail deep-link.
 * Custom domains (1691inc.com, etc.) fall through to `null` and just show
 * the "Resend" button without a one-click open-inbox CTA.
 */
const INBOX_PROVIDERS = {
  "gmail.com":        { name: "Gmail",   url: "https://mail.google.com/mail/u/0/#inbox" },
  "googlemail.com":   { name: "Gmail",   url: "https://mail.google.com/mail/u/0/#inbox" },
  "outlook.com":      { name: "Outlook", url: "https://outlook.live.com/mail/0/inbox" },
  "hotmail.com":      { name: "Outlook", url: "https://outlook.live.com/mail/0/inbox" },
  "live.com":         { name: "Outlook", url: "https://outlook.live.com/mail/0/inbox" },
  "msn.com":          { name: "Outlook", url: "https://outlook.live.com/mail/0/inbox" },
  "yahoo.com":        { name: "Yahoo",   url: "https://mail.yahoo.com/d/folders/1" },
  "ymail.com":        { name: "Yahoo",   url: "https://mail.yahoo.com/d/folders/1" },
  "icloud.com":       { name: "iCloud",  url: "https://www.icloud.com/mail" },
  "me.com":           { name: "iCloud",  url: "https://www.icloud.com/mail" },
  "mac.com":          { name: "iCloud",  url: "https://www.icloud.com/mail" },
  "aol.com":          { name: "AOL",     url: "https://mail.aol.com/" },
  "proton.me":        { name: "Proton",  url: "https://mail.proton.me/inbox" },
  "protonmail.com":   { name: "Proton",  url: "https://mail.proton.me/inbox" },
  "pm.me":            { name: "Proton",  url: "https://mail.proton.me/inbox" },
  "fastmail.com":     { name: "Fastmail",url: "https://app.fastmail.com/mail/Inbox" },
  "fastmail.fm":      { name: "Fastmail",url: "https://app.fastmail.com/mail/Inbox" },
};

function providerFor(email) {
  if (!email || !email.includes("@")) return null;
  const domain = email.split("@")[1].toLowerCase();
  return INBOX_PROVIDERS[domain] || null;
}

/**
 * Inline "Verify your email" banner. Renders only when:
 *   - a user is signed in
 *   - their email is NOT yet verified
 *
 * Now offers a one-click "Open Gmail/Outlook/…" deep-link for the 95% of
 * users on a major consumer provider — so they skip the tab-hunt entirely.
 */
export default function VerifyEmailBanner() {
  const { user, refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  if (!user) return null;
  if (user.email_verified) return null;

  const provider = providerFor(user.email);

  const resend = async () => {
    setBusy(true);
    try {
      await api.post("/auth/email/verify/request", { email: user.email });
      setSent(true);
      toast.success("Verification link sent. Check your inbox.");
      // Refresh /me in case the user verified in another tab while we wait.
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send. Try again.");
    } finally { setBusy(false); }
  };

  return (
    <div
      data-testid="verify-email-banner"
      className="border border-gold/40 bg-cream rounded-sm px-4 py-3 sm:px-5 sm:py-4 mb-8 flex items-start sm:items-center justify-between gap-3 flex-wrap"
    >
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-gold shrink-0 mt-0.5 sm:mt-0" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
        <div className="min-w-0">
          <p className="font-sans text-sm font-semibold ink">Verify your email</p>
          <p className="font-serif text-sm text-muted-ink leading-relaxed">
            We sent a link to <strong className="ink/90">{user.email}</strong>. Click it to unlock posting and joining.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 flex-wrap">
        {provider && (
          <a
            href={provider.url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="verify-email-open-inbox"
            className="inline-flex items-center gap-1.5 bg-gold text-cream font-sans text-xs uppercase tracking-[0.18em] font-semibold px-3 py-2 rounded-sm hover:opacity-90 transition-opacity"
          >
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M14 3h7v7M10 14L21 3M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" />
            </svg>
            Open {provider.name}
          </a>
        )}
        <button
          type="button"
          onClick={resend}
          disabled={busy || sent}
          data-testid="verify-email-resend"
          className="font-sans text-xs uppercase tracking-[0.18em] font-semibold border hairline px-3 py-2 rounded-sm hover:bg-gold hover:text-cream hover:border-gold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? "Sending…" : sent ? "Sent" : "Resend"}
        </button>
      </div>
    </div>
  );
}
