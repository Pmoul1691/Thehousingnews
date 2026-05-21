import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";

/**
 * Admin-only floating panel on /news showing what visitors are reading right
 * now: top articles by clicks in the last 24h, total impressions on the
 * page, and a rough "currently viewing" count (distinct sessions seen in
 * the last 60s).
 *
 * Renders only when the viewer is an admin. Polls every 30s while open.
 */
export default function NewsAdminPulse({ enabled }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastFetched, setLastFetched] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get("/agg/admin/news-pulse", { params: { hours: 24, limit: 10 } });
      setData(r.data);
      setLastFetched(new Date());
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not load pulse");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled || !open) return undefined;
    refresh();
    const t = setInterval(refresh, 30000);
    return () => clearInterval(t);
  }, [enabled, open, refresh]);

  if (!enabled) return null;

  return (
    <div
      data-testid="news-admin-pulse"
      className="fixed bottom-24 right-6 z-40 font-sans sm:bottom-28 sm:right-8"
      style={{ width: open ? "min(420px, calc(100vw - 32px))" : "auto" }}
    >
      {!open ? (
        <button
          type="button"
          data-testid="news-admin-pulse-open"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-agg-navy text-white text-[11px] uppercase tracking-[0.18em] font-semibold shadow-xl hover:bg-agg-navy-deep transition-colors"
        >
          <span aria-hidden="true">📊</span>
          Pulse
        </button>
      ) : (
        <section
          data-testid="news-admin-pulse-panel"
          className="bg-white border border-agg-navy/10 rounded-lg shadow-2xl overflow-hidden"
        >
          <header className="flex items-center justify-between px-4 py-3 bg-agg-navy text-white">
            <div className="min-w-0">
              <p className="text-[9px] uppercase tracking-[0.22em] font-semibold opacity-80">
                Admin pulse · last 24h
              </p>
              <p className="font-display font-semibold text-base">What the room is reading</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                data-testid="news-admin-pulse-refresh"
                onClick={refresh}
                disabled={loading}
                aria-label="Refresh pulse"
                className="p-1.5 rounded-sm hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                <svg viewBox="0 0 24 24" className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="23 4 23 10 17 10" />
                  <polyline points="1 20 1 14 7 14" />
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                </svg>
              </button>
              <button
                type="button"
                data-testid="news-admin-pulse-close"
                onClick={() => setOpen(false)}
                aria-label="Close pulse"
                className="p-1.5 rounded-sm hover:bg-white/10 transition-colors"
              >
                <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </header>

          <div className="max-h-[60vh] overflow-y-auto">
            {/* Top-line stats */}
            <div className="grid grid-cols-3 gap-px bg-slate-100 border-b border-slate-200">
              <Stat label="Live now" value={data?.totals?.live_visitors ?? "—"} testid="pulse-live" />
              <Stat label="Clicks 24h" value={data?.totals?.clicks ?? "—"} testid="pulse-clicks" />
              <Stat label="Impressions 24h" value={data?.totals?.impressions ?? "—"} testid="pulse-impressions" />
            </div>

            {/* Top article list */}
            <div className="p-4">
              <p className="text-[9px] uppercase tracking-[0.22em] font-semibold text-slate-500 mb-3">
                Top 10 articles by clicks
              </p>
              {error && (
                <p data-testid="news-admin-pulse-error" className="text-xs text-red-700">{error}</p>
              )}
              {!error && (!data || data.items.length === 0) && (
                <p className="text-xs text-slate-500 italic">No clicks yet in the last 24 hours.</p>
              )}
              {data && data.items.length > 0 && (
                <ol className="space-y-2.5" data-testid="news-admin-pulse-list">
                  {data.items.map((it, i) => (
                    <li key={it.article_id} className="flex items-start gap-2 text-xs">
                      <span className="font-mono text-[10px] text-slate-400 tabular-nums w-5 shrink-0 pt-0.5">{i + 1}.</span>
                      <div className="min-w-0 flex-1">
                        <a
                          href={it.original_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-agg-navy hover:text-agg-orange transition-colors block font-display font-semibold text-[13px] leading-snug truncate"
                          title={it.title}
                        >
                          {it.title || "(untitled)"}
                        </a>
                        <p className="text-[10px] text-slate-500 mt-0.5 truncate">
                          {it.publisher?.name || "—"}
                        </p>
                      </div>
                      <div className="text-right shrink-0 pl-2">
                        <p className="font-mono tabular-nums text-[12px] text-agg-orange font-semibold leading-none">
                          {it.clicks}
                        </p>
                        <p className="font-mono tabular-nums text-[9px] text-slate-400 leading-none mt-1">
                          {it.impressions} imp
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>

          <footer className="px-4 py-2 border-t border-slate-100 bg-slate-50 text-[10px] text-slate-500 flex items-center justify-between">
            <span>{lastFetched ? `Updated ${lastFetched.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}` : "Loading…"}</span>
            <span>Auto-refresh 30s</span>
          </footer>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value, testid }) {
  return (
    <div className="bg-white px-3 py-3 text-center" data-testid={testid}>
      <p className="font-display font-semibold text-xl text-agg-navy tabular-nums leading-none">{value}</p>
      <p className="text-[9px] uppercase tracking-[0.18em] font-semibold text-slate-500 mt-1">{label}</p>
    </div>
  );
}
