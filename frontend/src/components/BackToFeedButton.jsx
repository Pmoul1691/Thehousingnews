import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

/**
 * "Back to feed" pill button shown when a member is signed in.
 * Sits at the top-left of the viewport, just under the sticky header.
 * Hidden on /feed itself and for unauthenticated visitors.
 *
 * Mobile: shows just the arrow + "Feed".
 * Desktop: shows "← Back to Feed".
 */
export default function BackToFeedButton() {
  const { user } = useAuth();
  const loc = useLocation();

  const authed = user && user.status === "approved";
  const onFeed = loc.pathname === "/feed";

  if (!authed || onFeed) return null;

  return (
    <Link
      to="/feed"
      data-testid="back-to-feed-btn"
      aria-label="Back to feed"
      className="fixed left-3 sm:left-6 top-[72px] sm:top-[84px] z-30 inline-flex items-center gap-1.5 bg-cream/95 backdrop-blur border border-gold/40 text-ink font-sans font-semibold text-[11px] sm:text-xs uppercase tracking-[0.12em] px-3 py-1.5 rounded-full shadow-sm hover:bg-gold hover:text-cream hover:border-gold transition-colors"
    >
      <svg viewBox="0 0 24 24" className="w-3 h-3 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
        <path d="M19 12H5M12 19l-7-7 7-7" />
      </svg>
      <span className="hidden sm:inline">Back to feed</span>
      <span className="sm:hidden">Feed</span>
    </Link>
  );
}
