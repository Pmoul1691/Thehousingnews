import { useEffect } from "react";

/**
 * Prefetch the JS chunks for the next 2-3 most-likely-clicked routes once
 * the current page is idle. After Day-2 code splitting, every route lives
 * in its own webpack chunk, so the first click into a new route pays the
 * chunk-fetch cost on top of the route-data fetch. This component starts
 * those fetches in the background, so by the time the user clicks a CTA
 * the chunk is already in the cache.
 *
 * Usage:
 *   <RoutePrefetch
 *     loaders={[
 *       () => import("@/pages/AggHome"),
 *       () => import("@/pages/SignIn"),
 *       () => import("@/pages/About"),
 *     ]}
 *   />
 *
 * Loaders run **after** `requestIdleCallback` (or a 600ms fallback) so they
 * never compete with the current page's own render or data fetches. Each
 * loader runs once; failures are silent — prefetch is best-effort.
 */
export default function RoutePrefetch({ loaders = [] }) {
  useEffect(() => {
    if (typeof window === "undefined" || !loaders.length) return undefined;

    // Don't prefetch on tiny / slow connections — respect Save-Data and
    // 2g/slow-2g. Saves bandwidth for users who can least afford it.
    try {
      const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (conn && (conn.saveData || /^(slow-)?2g$/.test(conn.effectiveType || ""))) {
        return undefined;
      }
    } catch { /* ignore */ }

    let cancelled = false;
    const run = () => {
      if (cancelled) return;
      loaders.forEach((load) => {
        try { Promise.resolve(load()).catch(() => {}); } catch { /* ignore */ }
      });
    };

    let idleHandle = null;
    let timerHandle = null;
    if (typeof window.requestIdleCallback === "function") {
      idleHandle = window.requestIdleCallback(run, { timeout: 2000 });
    } else {
      timerHandle = setTimeout(run, 600);
    }

    return () => {
      cancelled = true;
      if (idleHandle && typeof window.cancelIdleCallback === "function") {
        try { window.cancelIdleCallback(idleHandle); } catch { /* ignore */ }
      }
      if (timerHandle) clearTimeout(timerHandle);
    };
  }, [loaders]);

  return null;
}
