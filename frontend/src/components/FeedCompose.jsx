import React, { useEffect, useRef, useState } from "react";
import { API } from "@/lib/api";
import Composer from "@/components/Composer";

/**
 * FeedCompose
 *
 * Facebook-style collapsed compose card that expands into the full Composer
 * on click. When collapsed it shows the user's avatar + a pseudo-input
 * prompt + a row of quick-action chips. On click anywhere in the collapsed
 * card the full Composer renders in place.
 *
 * The collapsed state is the "obvious" entry point - it tells a returning
 * member "this is how you post" without forcing the heavy Composer chrome
 * on them every time they open the feed.
 */
export default function FeedCompose({ user, profile, onPosted }) {
  const [expanded, setExpanded] = useState(false);
  const wrapRef = useRef(null);

  // Scroll the expanded composer into view on first expand
  useEffect(() => {
    if (expanded && wrapRef.current) {
      wrapRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [expanded]);

  const firstName = (user?.name || "").split(" ")[0] || "there";
  const avatarUrl = profile?.avatar_path ? `${API}/uploads/file/${profile.avatar_path}` : null;

  // Stub-profile users (just claimed their Brevo invite) can read the feed
  // but cannot post yet. We replace the collapsed compose UI with a quiet
  // prompt that links to /onboarding instead of expanding into the composer.
  if (profile?.is_stub) {
    return (
      <section data-testid="feed-compose-locked" className="mb-12">
        <div className="flex items-center gap-4 py-5 border-b hairline">
          <div className="w-11 h-11 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
            <span className="font-display text-base text-gold">{(user?.name || "M")[0].toUpperCase()}</span>
          </div>
          <a
            href="/onboarding"
            data-testid="feed-compose-locked-cta"
            className="flex-1 text-left font-serif italic text-lg text-[#2C2410]/60 hover:text-gold transition-colors"
          >
            Finish setup to start writing →
          </a>
        </div>
      </section>
    );
  }

  if (expanded) {
    return (
      <section ref={wrapRef} data-testid="feed-compose-expanded" className="mb-12">
        <div className="flex items-center justify-between mb-3">
          <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-gold">Write</p>
          <button
            type="button"
            data-testid="feed-compose-collapse"
            onClick={() => setExpanded(false)}
            aria-label="Close compose"
            className="inline-flex items-center gap-1.5 font-sans text-xs font-medium text-muted-ink hover:text-gold transition-colors px-3 py-1.5"
          >
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
            Close
          </button>
        </div>
        <Composer onPosted={() => { onPosted && onPosted(); }} />
      </section>
    );
  }

  return (
    <section data-testid="feed-compose-collapsed" className="mb-12">
      <div className="flex items-center gap-4 py-5 border-b hairline">
        <div className="w-11 h-11 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            <span className="font-display text-base text-gold">
              {(user?.name || "M")[0].toUpperCase()}
            </span>
          )}
        </div>
        <button
          type="button"
          data-testid="feed-compose-trigger"
          onClick={() => setExpanded(true)}
          className="flex-1 text-left font-serif italic text-lg text-[#2C2410]/45 hover:text-[#2C2410]/70 transition-colors"
        >
          Write something, {firstName}...
        </button>
        <div className="hidden sm:flex items-center gap-1">
          <button
            type="button"
            data-testid="feed-compose-quick-photo"
            onClick={() => setExpanded(true)}
            className="inline-flex items-center gap-1.5 font-sans text-xs font-medium text-muted-ink hover:text-gold transition-colors px-3 py-1.5"
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <circle cx="9" cy="11" r="2" />
              <path d="M3 17l5-5 4 4 3-3 6 6" />
            </svg>
            Photo
          </button>
          <button
            type="button"
            data-testid="feed-compose-quick-video"
            onClick={() => setExpanded(true)}
            className="inline-flex items-center gap-1.5 font-sans text-xs font-medium text-muted-ink hover:text-gold transition-colors px-3 py-1.5"
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <rect x="3" y="6" width="14" height="12" rx="2" />
              <path d="M17 10l4-2v8l-4-2z" />
            </svg>
            Video
          </button>
          <button
            type="button"
            data-testid="feed-compose-quick-essay"
            onClick={() => setExpanded(true)}
            className="inline-flex items-center gap-1.5 font-sans text-xs font-medium text-muted-ink hover:text-gold transition-colors px-3 py-1.5"
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <path d="M4 4h12l4 4v12H4z" />
              <path d="M8 12h8M8 16h8M8 8h4" />
            </svg>
            Essay
          </button>
        </div>
      </div>
    </section>
  );
}
