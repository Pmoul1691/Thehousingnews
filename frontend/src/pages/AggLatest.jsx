import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AggLayout from "@/components/AggLayout";
import api from "@/lib/api";

/**
 * /news/latest — flat "river" of individual articles across every active
 * publisher. Per the RSS-aggregator spec: each card shows headline, source,
 * date, excerpt, image (when available). All clicks open the publisher URL
 * in a new tab; we never link to an internal article view.
 *
 * Filters: category, source, free-text search. Pagination via offset/limit.
 */

const CATEGORY_LABELS = {
  national_trade: "National",
  regional: "Regional",
  industry_blog: "Blog",
  data_research: "Data",
  mortgage: "Mortgage",
  newsletter: "Newsletter",
  commercial_re: "Commercial",
};

const PAGE_SIZE = 20;
const HOURS_WINDOW = 168; // last 7 days

function formatWhen(iso) {
  if (!iso) return "";
  const t = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now - t) / 1000);
  if (diff < 3600) return `${Math.max(1, Math.floor(diff / 60))}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d`;
  return t.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function hostFromUrl(u) {
  try { return new URL(u).hostname.replace(/^www\./, ""); }
  catch { return ""; }
}

function ArticleCard({ item }) {
  const pub = item.publisher || {};
  const host = hostFromUrl(item.original_url);
  const favicon = pub.logo_url || (host ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64` : null);
  return (
    <li>
      <a
        href={item.original_url}
        target="_blank"
        rel="noopener noreferrer"
        data-testid={`agg-latest-card-${item.id}`}
        className="group block bg-white border border-slate-200 rounded-sm overflow-hidden hover:border-agg-orange hover:-translate-y-0.5 transition-all duration-200 h-full flex flex-col"
      >
        {item.thumbnail_url && (
          <div className="aspect-[16/9] bg-slate-100 overflow-hidden">
            <img
              src={item.thumbnail_url}
              alt=""
              loading="lazy"
              className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-300"
              onError={(e) => { e.currentTarget.parentElement.style.display = "none"; }}
            />
          </div>
        )}
        <div className="p-4 flex flex-col flex-1">
          <div className="flex items-center gap-2 mb-2">
            {favicon && (
              <img src={favicon} alt="" width={14} height={14} className="w-3.5 h-3.5 rounded-sm" />
            )}
            <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-agg-orange truncate">
              {pub.name || host}
            </span>
            {pub.category && CATEGORY_LABELS[pub.category] && (
              <span className="font-sans text-[9px] uppercase tracking-[0.16em] text-slate-500 border border-slate-200 px-1.5 py-0.5 rounded-sm">
                {CATEGORY_LABELS[pub.category]}
              </span>
            )}
            <span className="ml-auto font-mono text-[10px] text-slate-500 shrink-0">{formatWhen(item.published_at)}</span>
          </div>
          <h3 className="font-display font-semibold text-[17px] leading-snug text-agg-navy group-hover:text-agg-orange transition-colors line-clamp-3">
            {item.title}
          </h3>
          {item.snippet && (
            <p className="font-serif text-[14px] leading-relaxed text-slate-700 mt-2 line-clamp-3">
              {item.snippet}
            </p>
          )}
        </div>
      </a>
    </li>
  );
}

export default function AggLatest() {
  const [params, setParams] = useSearchParams();
  const initialCategory = params.get("category") || "";
  const initialSource = params.get("source") || "";
  const initialSearch = params.get("q") || "";

  const [category, setCategory] = useState(initialCategory);
  const [source, setSource] = useState(initialSource);
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [search, setSearch] = useState(initialSearch);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [publishers, setPublishers] = useState([]);

  // Persist active filters in the URL bar so back/forward works.
  useEffect(() => {
    const next = new URLSearchParams();
    if (category) next.set("category", category);
    if (source) next.set("source", source);
    if (search) next.set("q", search);
    setParams(next, { replace: true });
    setOffset(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, source, search]);

  // Load publisher list (for the source dropdown).
  useEffect(() => {
    api.get("/agg/publishers").then((r) => setPublishers(r.data.items || [])).catch(() => {});
  }, []);

  // Fetch articles whenever a filter or offset changes.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const args = { hours: HOURS_WINDOW, limit: PAGE_SIZE, offset };
    if (category) args.category = category;
    if (source) args.publisher_slug = source;
    if (search) args.search = search;
    api
      .get("/agg/articles", { params: args })
      .then((r) => {
        if (!alive) return;
        setItems(r.data.items || []);
        setTotal(r.data.total || 0);
      })
      .catch(() => alive && setItems([]))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [category, source, search, offset]);

  const groupedPublishers = useMemo(() => {
    const grouped = {};
    publishers.forEach((p) => {
      const k = p.category || "uncategorized";
      grouped[k] = grouped[k] || [];
      grouped[k].push(p);
    });
    Object.values(grouped).forEach((arr) => arr.sort((a, b) => a.name.localeCompare(b.name)));
    return grouped;
  }, [publishers]);

  const submitSearch = (e) => {
    e.preventDefault();
    setSearch(searchInput.trim());
  };

  const hasNext = offset + PAGE_SIZE < total;
  const hasPrev = offset > 0;

  return (
    <AggLayout>
      <section data-testid="agg-latest-hero">
        <p className="font-sans text-[10px] uppercase tracking-[0.28em] font-semibold text-agg-orange">The Daily · Latest</p>
        <h1 className="font-display font-semibold text-[32px] sm:text-[40px] leading-[1.05] text-agg-navy mt-3 tracking-tight">
          Every story, every source.
        </h1>
        <p className="font-serif text-[15px] sm:text-[16px] leading-[1.55] text-slate-700 mt-3 max-w-3xl">
          A flat river of every article pulled from {publishers.length || "—"} housing sources in the last 7 days.
          Click any card to read it at the publisher.
        </p>
      </section>

      <section className="mt-8 pb-5 border-b border-slate-200">
        <form onSubmit={submitSearch} className="flex flex-col sm:flex-row sm:items-center gap-3" data-testid="agg-latest-filters">
          <div className="flex-1">
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search headlines or excerpts…"
              data-testid="agg-latest-search-input"
              className="w-full bg-white border border-slate-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-agg-orange"
            />
          </div>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            data-testid="agg-latest-category-select"
            className="bg-white border border-slate-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-agg-orange"
          >
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            data-testid="agg-latest-source-select"
            className="bg-white border border-slate-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-agg-orange max-w-[200px]"
          >
            <option value="">All sources</option>
            {Object.entries(groupedPublishers).map(([cat, list]) => (
              <optgroup key={cat} label={CATEGORY_LABELS[cat] || cat}>
                {list.map((p) => (
                  <option key={p.slug} value={p.slug}>{p.name}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <button
            type="submit"
            data-testid="agg-latest-search-submit"
            className="bg-agg-orange text-agg-navy font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity"
          >
            Search
          </button>
        </form>
        {(category || source || search) && (
          <button
            type="button"
            onClick={() => { setCategory(""); setSource(""); setSearch(""); setSearchInput(""); }}
            data-testid="agg-latest-clear-filters"
            className="mt-3 font-sans text-[12px] text-slate-500 hover:text-agg-orange transition-colors"
          >
            Clear filters →
          </button>
        )}
      </section>

      <section className="py-8" data-testid="agg-latest-results">
        {loading ? (
          <p className="text-slate-500 py-12 text-center font-sans text-sm" data-testid="agg-latest-loading">Loading…</p>
        ) : items.length === 0 ? (
          <div className="py-16 text-center" data-testid="agg-latest-empty">
            <p className="font-display text-lg text-agg-navy">No articles match those filters.</p>
            <p className="font-sans text-sm text-slate-500 mt-2">Try widening the category, picking a different source, or clearing the search.</p>
          </div>
        ) : (
          <>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-5">
              Showing {offset + 1}–{Math.min(offset + items.length, total)} of {total}
            </p>
            <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {items.map((it) => (
                <ArticleCard key={it.id} item={it} />
              ))}
            </ul>
            <div className="flex items-center justify-between mt-10">
              <button
                type="button"
                disabled={!hasPrev}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                data-testid="agg-latest-prev"
                className="font-sans text-sm font-semibold text-agg-navy disabled:text-slate-300 hover:text-agg-orange transition-colors"
              >
                ← Newer
              </button>
              <span className="font-mono text-[11px] text-slate-500">
                Page {Math.floor(offset / PAGE_SIZE) + 1}
              </span>
              <button
                type="button"
                disabled={!hasNext}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                data-testid="agg-latest-next"
                className="font-sans text-sm font-semibold text-agg-navy disabled:text-slate-300 hover:text-agg-orange transition-colors"
              >
                Older →
              </button>
            </div>
          </>
        )}
      </section>

      <section className="pt-8 border-t border-slate-200">
        <p className="font-sans text-[12px] text-slate-500">
          Looking for a single source?{" "}
          <Link to="/news" className="text-agg-orange hover:underline">Browse the publisher grid →</Link>
        </p>
      </section>
    </AggLayout>
  );
}
