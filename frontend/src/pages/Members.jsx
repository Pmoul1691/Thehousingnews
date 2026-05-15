import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";

const FILTER_OPTIONS = [
  { key: "", label: "Everyone" },
  { key: "comped", label: "Comped (Partners)" },
  { key: "supporter", label: "Stripe supporter" },
  { key: "free", label: "Free members" },
];

function EntitlementChip({ entitlement }) {
  if (!entitlement) return null;
  const map = {
    comped: { label: "Comped", cls: "border-gold text-gold" },
    supporter: { label: "Supporter", cls: "border-deepred text-deepred" },
    free: { label: "Free", cls: "border-muted-ink text-muted-ink" },
  };
  const m = map[entitlement.tier] || map.free;
  return (
    <span
      className={`inline-flex items-center gap-1 font-sans text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-sm border ${m.cls}`}
      data-testid={`member-tier-${entitlement.tier}`}
      title={entitlement.partner_tier || entitlement.source || ""}
    >
      {m.label}
    </span>
  );
}

export default function Members() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    setFetching(true);
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (filter && user.is_admin) params.set("filter", filter);
    api.get(`/members${params.toString() ? `?${params.toString()}` : ""}`)
      .then((r) => setItems(r.data.items || []))
      .finally(() => setFetching(false));
  }, [user, loading, navigate, q, filter]);

  return (
    <div className="container-prose py-12">
      <p className="uppercase-label mb-3">Directory</p>
      <h1 className="font-display font-semibold text-3xl ink mb-6">Members of the newsroom.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-10">
        Real people, in real markets. Search by name or city. No follower counts. Follow whoever you want to read.
      </p>

      <input
        data-testid="members-search"
        placeholder="Search by name or market"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold mb-4"
      />

      {user?.is_admin && (
        <div className="mb-10 flex flex-wrap items-center gap-2" data-testid="members-admin-filter">
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold mr-1">
            Admin filter
          </span>
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.key || "all"}
              type="button"
              data-testid={`members-filter-${opt.key || "all"}`}
              onClick={() => setFilter(opt.key)}
              className={`font-sans text-xs px-3 py-1 rounded-full border transition-colors ${
                filter === opt.key
                  ? "bg-gold text-cream border-gold"
                  : "hairline text-ink hover:border-gold hover:text-gold"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {fetching ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="members-empty">
          <p className="font-serif text-base ink/80">No members match that search.</p>
        </div>
      ) : (
        <ul className="divide-y divide-[#E8D4A0] border-t border-b hairline">
          {items.map((m) => {
            const avatarUrl = m.avatar_path ? `${API}/uploads/file/${m.avatar_path}` : null;
            return (
              <li key={m.user_id} data-testid={`member-${m.user_id}`} className="py-6 flex items-start gap-4">
                <div className="w-12 h-12 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
                  {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
                    <span className="font-display text-lg text-gold">{(m.name || "M")[0]}</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Link to={`/profile/${m.user_id}`} className="font-display font-semibold text-base ink hover:text-gold transition-colors">{m.name}</Link>
                    <EntitlementChip entitlement={m.entitlement} />
                  </div>
                  <div className="font-sans text-xs text-muted-ink">{m.market}</div>
                  {user?.is_admin && m.entitlement?.email && (
                    <div className="font-mono text-[11px] text-muted-ink mt-0.5">{m.entitlement.email}</div>
                  )}
                  {m.bio && <p className="prose-serif text-sm ink/80 leading-relaxed mt-2 line-clamp-2">{m.bio}</p>}
                </div>
                <Link to={`/profile/${m.user_id}`} className="font-sans text-sm font-medium text-gold hover:opacity-80 whitespace-nowrap">View</Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
