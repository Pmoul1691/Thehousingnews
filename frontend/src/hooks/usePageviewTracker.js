import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import api from "@/lib/api";

/**
 * Fires one pageview event to /api/events/pageview on every React Router
 * navigation. Best-effort: failures are swallowed silently so analytics
 * never breaks user flow.
 *
 * Mount once at the top of App. Generates a per-tab session_id stored in
 * sessionStorage so multiple tabs each count as separate sessions.
 */
const SESSION_KEY = "thn_event_session";

function getSessionId() {
  try {
    let s = sessionStorage.getItem(SESSION_KEY);
    if (!s) {
      s = `s_${Math.random().toString(36).slice(2, 12)}_${Date.now().toString(36)}`;
      sessionStorage.setItem(SESSION_KEY, s);
    }
    return s;
  } catch {
    return null;
  }
}

export default function usePageviewTracker() {
  const location = useLocation();
  const lastPath = useRef(null);

  useEffect(() => {
    const path = location.pathname + location.search;
    if (lastPath.current === path) return;
    lastPath.current = path;
    const sid = getSessionId();
    // Don't await — fire and forget.
    api.post("/events/pageview", {
      path: location.pathname,
      session_id: sid,
      referrer: typeof document !== "undefined" ? document.referrer || null : null,
    }).catch(() => {});
  }, [location]);
}
