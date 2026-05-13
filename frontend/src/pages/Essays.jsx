import React, { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

function EssayRow({ e }) {
  const author = e.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const coverUrl = e.image_path ? `${API}/uploads/file/${e.image_path}` : null;
  return (
    <Link to={`/essays/${e.post_id}`} data-testid={`essay-row-${e.post_id}`} className="block group border-b hairline py-8 first:pt-0">
      <div className="flex gap-6">
        <div className="flex-1 min-w-0">
          {e.is_pete_pick && (
            <div className="flex items-center gap-2 mb-2">
              <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete pick</span>
            </div>
          )}
          <div className="flex items-center gap-3 mb-3">
            <div className="w-6 h-6 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
              {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
                <span className="font-display text-[10px] text-gold">{(author.name || "M")[0]}</span>
              )}
            </div>
            <span className="font-sans text-xs font-semibold ink">{author.name}</span>
            {author.market && <span className="font-sans text-xs text-muted-ink">. {author.market}</span>}
          </div>
          <h3 className="font-display font-semibold text-xl sm:text-2xl ink leading-tight group-hover:text-gold transition-colors mb-2">
            {e.title}
          </h3>
          {e.subtitle && (
            <p className="font-serif italic text-base text-[#2C2410]/75 mb-3 line-clamp-2">{e.subtitle}</p>
          )}
          {e.preview && (
            <p className="prose-serif text-sm text-[#2C2410]/80 leading-relaxed line-clamp-2 mb-3">{e.preview}</p>
          )}
          <div className="font-sans text-xs text-muted-ink">
            {formatDate(e.release_at || e.created_at)} . {e.word_count ? `${Math.max(1, Math.round(e.word_count / 220))} min read` : ""}
          </div>
        </div>
        {coverUrl && (
          <div className="hidden sm:block w-32 h-32 shrink-0 border hairline rounded-sm overflow-hidden">
            <img src={coverUrl} alt="" className="w-full h-full object-cover" />
          </div>
        )}
      </div>
    </Link>
  );
}

export default function Essays() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [market, setMarket] = useState(params.get("market") || "");
  const [items, setItems] = useState([]);
  const [picks, setPicks] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set("q", q.trim());
      if (market.trim()) qs.set("market", market.trim());
      const [list, p] = await Promise.all([
        api.get(`/essays${qs.toString() ? `?${qs.toString()}` : ""}`),
        api.get("/posts/picks?limit=3"),
      ]);
      setItems(list.data.items || []);
      // Only show essay picks here
      setPicks((p.data.items || []).filter((x) => x.kind === "essay"));
    } finally {
      setLoading(false);
    }
  }, [q, market]);

  useEffect(() => { load(); }, [load]);

  const onSearch = (e) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (q.trim()) next.set("q", q.trim());
    if (market.trim()) next.set("market", market.trim());
    setParams(next);
  };

  return (
    <div className="container-prose py-12">
      <div className="mb-10">
        <p className="uppercase-label mb-2">Library</p>
        <h1 className="font-display font-semibold text-4xl ink leading-tight">Essays from the room.</h1>
        <p className="font-serif text-base text-muted-ink mt-3 max-w-2xl">
          Long-form writing from working real estate operators. Calm, slow, unhurried. Search by topic or filter by market.
        </p>
      </div>

      <form onSubmit={onSearch} className="border hairline rounded-sm p-4 bg-cream mb-10 flex flex-col sm:flex-row gap-3" data-testid="essays-search">
        <input
          data-testid="essays-search-q"
          placeholder="Search title, subtitle, body"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <input
          data-testid="essays-search-market"
          placeholder="Market (e.g. Atlanta)"
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          className="sm:w-56 bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <button data-testid="essays-search-go" type="submit" className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity">
          Search
        </button>
      </form>

      {picks.length > 0 && !q && !market && (
        <section className="mb-12" data-testid="essays-picks">
          <div className="flex items-center gap-2 mb-5">
            <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete recommends</span>
            <span className="h-px flex-1 bg-gold-mid" />
          </div>
          <div className="grid sm:grid-cols-3 gap-6">
            {picks.map((p) => {
              const author = p.author || {};
              return (
                <Link key={p.post_id} to={`/essays/${p.post_id}`} data-testid={`pick-${p.post_id}`} className="block border hairline rounded-sm p-5 bg-cream hover:border-gold transition-colors group">
                  <p className="font-sans text-[10px] uppercase tracking-wider text-gold font-semibold mb-2">Essay</p>
                  <h4 className="font-display font-semibold text-lg ink leading-snug group-hover:text-gold transition-colors line-clamp-3 mb-3">
                    {p.title}
                  </h4>
                  <p className="font-sans text-xs text-muted-ink">{author.name}{author.market ? ` . ${author.market}` : ""}</p>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      <div data-testid="essays-list">
        {loading ? (
          <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
        ) : items.length === 0 ? (
          <div className="border hairline rounded-sm py-16 text-center" data-testid="essays-empty">
            <p className="uppercase-label mb-3">Nothing yet</p>
            <p className="font-serif text-base ink/80 max-w-prose mx-auto">
              No essays match. {user ? <>Try a different word or write the first one from <Link to="/write" className="text-gold underline underline-offset-4 decoration-gold-mid">your desk</Link>.</> : "Try a different word."}
            </p>
          </div>
        ) : (
          items.map((e) => <EssayRow key={e.post_id} e={e} />)
        )}
      </div>
    </div>
  );
}
