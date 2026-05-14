import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * Floating Write pill rendered on every authenticated page.
 * Hidden on the /write page itself and for unauthenticated visitors.
 * Polls /drafts/mine on mount + route change. If a draft exists, shows a
 * tiny indicator dot.
 */
export default function FloatingWriteButton() {
  const { user } = useAuth();
  const loc = useLocation();
  const [hasDraft, setHasDraft] = useState(false);

  const authed = user && user.status === "approved";
  const onWrite = loc.pathname.startsWith("/write");

  useEffect(() => {
    if (!authed || onWrite) return;
    let alive = true;
    api
      .get("/drafts/mine")
      .then((r) => {
        if (!alive) return;
        const d = r?.data || {};
        // Empty draft response is {}; treat anything with text/title/subtitle
        // content (or persisted media) as a real unfinished draft.
        const hasContent = !!(
          d.text?.trim() ||
          d.title?.trim() ||
          d.subtitle?.trim() ||
          (Array.isArray(d.media) && d.media.length > 0)
        );
        setHasDraft(hasContent);
      })
      .catch(() => {
        if (alive) setHasDraft(false);
      });
    return () => { alive = false; };
  }, [authed, onWrite, loc.pathname]);

  if (!authed || onWrite) return null;

  return (
    <Link
      to="/write"
      data-testid="floating-write-btn"
      aria-label={hasDraft ? "Write — you have a draft saved" : "Write"}
      className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 bg-gold text-cream font-sans font-semibold text-sm px-5 py-3 rounded-full shadow-lg hover:opacity-90 hover:-translate-y-0.5 transition-all sm:bottom-8 sm:right-8"
    >
      <span className="relative inline-flex items-center justify-center">
        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
        </svg>
        {hasDraft && (
          <span
            data-testid="floating-write-draft-dot"
            aria-label="Unfinished draft"
            className="absolute -top-1.5 -right-1.5 w-2.5 h-2.5 rounded-full bg-deepred border-2 border-cream"
          />
        )}
      </span>
      Write
    </Link>
  );
}
