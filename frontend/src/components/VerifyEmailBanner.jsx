import React, { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

/**
 * Inline "Verify your email" banner. Renders only when:
 *   - a user is signed in
 *   - their email is NOT yet verified
 * Clicking "Resend" re-issues a verification token via Brevo.
 */
export default function VerifyEmailBanner() {
  const { user, refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  if (!user) return null;
  if (user.email_verified) return null;

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
      <button
        type="button"
        onClick={resend}
        disabled={busy || sent}
        data-testid="verify-email-resend"
        className="font-sans text-xs uppercase tracking-[0.18em] font-semibold border hairline px-3 py-2 rounded-sm hover:bg-gold hover:text-cream hover:border-gold transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
      >
        {busy ? "Sending…" : sent ? "Sent" : "Resend"}
      </button>
    </div>
  );
}
