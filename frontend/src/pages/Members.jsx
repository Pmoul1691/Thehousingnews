import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";

export default function Members() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    setFetching(true);
    api.get(`/members${q ? `?q=${encodeURIComponent(q)}` : ""}`)
      .then((r) => setItems(r.data.items || []))
      .finally(() => setFetching(false));
  }, [user, loading, navigate, q]);

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
        className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold mb-10"
      />

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
                  <Link to={`/profile/${m.user_id}`} className="font-display font-semibold text-base ink hover:text-gold transition-colors">{m.name}</Link>
                  <div className="font-sans text-xs text-muted-ink">{m.market}</div>
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
