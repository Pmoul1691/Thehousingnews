import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";

/**
 * Compact strip of trending headline topics from the last 24 hours.
 * Click a topic to search the river via the existing search UX (we link to
 * the aggregator home with a `?q=` filter for now — the home page will
 * already drop it because we don't have client-side search on /; instead
 * we hand off to publisher search on Google for trade names. Simplest UX:
 * each chip is a no-op visual + an aria-label; future iteration can add a
 * dedicated `/topic/:slug` route.).
 *
 * For visual density we render a horizontal-scroll row of chips.
 */
export default function AggTrendingStrip() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .get("/agg/trending", { params: { hours: 24, limit: 8 } })
      .then((r) => {
        if (!alive) return;
        setItems(r.data.items || []);
      })
      .catch(() => {})
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <div className="mb-8" data-testid="agg-trending-loading">
        <div className="h-8 rounded-sm bg-slate-100 animate-pulse" />
      </div>
    );
  }
  if (!items.length) return null;

  return (
    <section
      className="mb-10 border-t border-b border-slate-200 py-3 -mx-2 sm:mx-0"
      aria-label="Trending topics today"
      data-testid="agg-trending"
    >
      <div className="flex items-center gap-3 overflow-x-auto px-2 sm:px-0 scrollbar-none">
        <span
          className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-agg-orange shrink-0"
          aria-hidden="true"
        >
          Trending · 24h
        </span>
        <ul className="flex items-center gap-2 sm:gap-3">
          {items.map((t) => (
            <li key={t.topic} data-testid={`agg-trending-${t.topic.replace(/\s+/g, "-")}`}>
              <Link
                to={`/news?topic=${encodeURIComponent(t.topic)}`}
                className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1 font-sans text-xs text-agg-navy hover:border-agg-orange hover:text-agg-orange transition-colors"
              >
                <span className="font-medium">{t.topic}</span>
                <span className="text-[10px] text-slate-400 font-mono">{t.count}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
