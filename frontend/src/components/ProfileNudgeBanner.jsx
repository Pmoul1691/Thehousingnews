import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

/**
 * Dismissable banner that nudges members who joined but haven't filled
 * out a real profile (name + market) to do so.
 *
 * The /members directory now surfaces profile-less signups with a
 * fallback email-prefix name — this banner is the friendly counterpart:
 * "your card looks sparse, take 30 seconds to fix it".
 *
 * Visibility rules:
 *  - Signed in
 *  - status === "approved"
 *  - profile_complete === false (per /api/auth/me)
 *  - Not already on /settings (no point nudging them where they're going)
 *  - Not on auth surfaces (signin, verify, magic link, claim)
 *  - Not dismissed within the past 7 days (localStorage)
 */
const DISMISS_KEY = "thn_profile_nudge_dismissed_until";
const DISMISS_DAYS = 7;
const HIDE_ON_PATHS = ["/signin", "/signup", "/auth", "/claim", "/settings"];

export default function ProfileNudgeBanner() {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if (loading) { setHidden(true); return; }
    if (!user || user.status !== "approved") { setHidden(true); return; }
    if (user.profile_complete) { setHidden(true); return; }
    if (HIDE_ON_PATHS.some((p) => location.pathname.startsWith(p))) { setHidden(true); return; }
    // localStorage dismissal
    try {
      const until = parseInt(localStorage.getItem(DISMISS_KEY) || "0", 10);
      if (until && until > Date.now()) { setHidden(true); return; }
    } catch { /* ignore */ }
    setHidden(false);
  }, [user, loading, location.pathname]);

  const dismiss = () => {
    try {
      const until = Date.now() + DISMISS_DAYS * 24 * 60 * 60 * 1000;
      localStorage.setItem(DISMISS_KEY, String(until));
    } catch { /* ignore */ }
    setHidden(true);
  };

  if (hidden) return null;

  return (
    <div
      data-testid="profile-nudge-banner"
      className="bg-gold/10 border-b border-gold/30"
    >
      <div className="container-wide flex items-center justify-between gap-4 py-3 flex-wrap">
        <p className="font-sans text-sm text-ink leading-snug">
          <span className="uppercase text-[10px] tracking-[0.18em] font-semibold text-gold mr-2">Members</span>
          Add a name and market so other members know who you are.
        </p>
        <div className="flex items-center gap-2">
          <Link
            to="/settings"
            data-testid="profile-nudge-cta"
            onClick={() => {
              try {
                if (typeof window !== "undefined" && typeof window.gtag === "function") {
                  window.gtag("event", "profile_nudge_clicked", { source: "banner" });
                }
              } catch { /* analytics never breaks UX */ }
            }}
            className="bg-gold text-cream font-sans font-semibold text-xs uppercase tracking-wider px-4 py-1.5 rounded-full hover:opacity-90 transition-opacity"
          >
            Complete profile
          </Link>
          <button
            type="button"
            data-testid="profile-nudge-dismiss"
            onClick={dismiss}
            className="text-muted-ink hover:text-ink p-1.5 -m-1.5"
            aria-label="Dismiss profile nudge for 7 days"
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
