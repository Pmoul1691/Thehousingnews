import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import PostItem from "@/components/PostItem";

const KINDS = [
  { k: "", l: "Everything" },
  { k: "essay", l: "Essays" },
  { k: "post", l: "Short posts" },
];

export default function Search() {
  const [params, setParams] = useSearchParams();
  const initialQ = params.get("q") || "";
  const initialKind = params.get("kind") || "";
  const initialMarket = params.get("market") || "";

  const [q, setQ] = useState(initialQ);
  const [market, setMarket] = useState(initialMarket);
  const [kind, setKind] = useState(initialKind);
  const [items, setItems] = useState([]);
  const [fetching, setFetching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (query, k, m) => {
    if (!query || query.trim().length < 2) {
      setItems([]);
      setSearched(false);
      return;
    }
    setFetching(true);
    setError(null);
    try {
      const r = await api.get("/posts/search", {
        params: { q: query.trim(), kind: k || undefined, market: m || undefined },
      });
      setItems(r.data.items || []);
      setSearched(true);
    } catch (e) {
      setError(e?.response?.data?.detail || "Search failed");
      setItems([]);
      setSearched(true);
    } finally {
      setFetching(false);
    }
  }, []);

  // Run when URL params change (back/forward, initial load)
  useEffect(() => {
    if (initialQ) run(initialQ, initialKind, initialMarket);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSubmit = (e) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (q.trim()) next.set("q", q.trim());
    if (kind) next.set("kind", kind);
    if (market.trim()) next.set("market", market.trim());
    setParams(next, { replace: true });
    run(q, kind, market);
  };

  return (
    <div className="container-prose py-12" data-testid="search-page">
      <p className="uppercase-label mb-3">Search</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-2 leading-tight">
        Find a post, an essay, a market.
      </h1>
      <p className="prose-serif text-base text-muted-ink mb-8 max-w-prose">
        Full-text search across the room. Title and subtitle weighted highest.
      </p>

      <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-3 mb-6" data-testid="search-form">
        <input
          autoFocus
          data-testid="search-input-q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Two-character minimum, like 'pricing'"
          className="flex-1 bg-cream border hairline rounded-sm px-4 py-3 font-serif text-base ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <input
          data-testid="search-input-market"
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          placeholder="Market (optional)"
          className="sm:w-48 bg-cream border hairline rounded-sm px-4 py-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <button
          type="submit"
          data-testid="search-submit"
          className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity"
        >
          Search
        </button>
      </form>

      <div className="flex items-center gap-4 mb-10 border-b hairline">
        {KINDS.map((t) => (
          <button
            key={t.k || "all"}
            data-testid={`search-kind-${t.k || "all"}`}
            onClick={() => {
              setKind(t.k);
              if (q.trim()) {
                const next = new URLSearchParams(params);
                if (t.k) next.set("kind", t.k); else next.delete("kind");
                setParams(next, { replace: true });
                run(q, t.k, market);
              }
            }}
            className={`pb-3 font-sans text-sm font-medium transition-colors ${
              kind === t.k ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"
            }`}
          >
            {t.l}
          </button>
        ))}
      </div>

      {error && (
        <div data-testid="search-error" className="border hairline rounded-sm p-5 mb-6 font-serif text-base text-deepred bg-[#FBF6E8]">
          {error}
        </div>
      )}

      {fetching ? (
        <div className="font-serif italic text-base text-muted-ink py-16 text-center" data-testid="search-loading">
          Looking.
        </div>
      ) : !searched ? (
        <p className="font-serif italic text-base text-muted-ink py-12 text-center" data-testid="search-prompt">
          Type a phrase and hit search.
        </p>
      ) : items.length === 0 ? (
        <div className="py-20 text-center" data-testid="search-empty">
          <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">Nothing</p>
          <p className="font-serif italic text-base text-[#2C2410]/65 max-w-prose mx-auto">
            No posts match &quot;{q}&quot;.
            {market ? ` Also filtered by market &quot;${market}&quot;.` : ""}
          </p>
        </div>
      ) : (
        <div data-testid="search-results">
          <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-4">
            {items.length} {items.length === 1 ? "result" : "results"}
          </p>
          <div>
            {items.map((p) => (
              <PostItem key={p.post_id} post={p} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
