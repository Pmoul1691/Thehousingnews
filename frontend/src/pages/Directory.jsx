import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import PageMeta from "@/components/PageMeta";
import { toast } from "sonner";

/**
 * Member Directory — searchable grid of approved members.
 * Shows current role (LinkedIn-imported when available), market, bio,
 * essay count, and a deep link to the member's profile.
 *
 * Auth: any approved member can view.
 */

function Initials({ name }) {
  const parts = (name || "").split(" ").filter(Boolean);
  const ini = parts.length >= 2 ? (parts[0][0] + parts[1][0]) : (name || "?").slice(0, 2);
  return (
    <div className="w-12 h-12 rounded-sm bg-ink text-cream flex items-center justify-center font-display font-semibold text-base shrink-0">
      {ini.toUpperCase()}
    </div>
  );
}

function MemberCard({ m }) {
  const meta = [m.current_role, m.current_company].filter(Boolean).join(" · ");
  return (
    <article
      data-testid={`directory-member-${m.user_id}`}
      className="bg-cream-soft border border-gold/15 rounded-sm p-5 hover:border-gold transition-colors"
    >
      <div className="flex items-start gap-3">
        {m.avatar_path ? (
          <img
            src={m.avatar_path}
            alt={m.name}
            className="w-12 h-12 rounded-sm object-cover bg-white shrink-0 border border-ink/10"
            onError={(e) => { e.target.style.display = "none"; }}
          />
        ) : (
          <Initials name={m.name} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <Link
              to={`/profile/${m.user_id}`}
              className="font-display font-semibold text-base ink hover:text-gold transition-colors truncate"
              data-testid={`directory-name-${m.user_id}`}
            >
              {m.name || "—"}
            </Link>
            {m.is_admin ? (
              <span className="font-mono text-[9px] uppercase tracking-wider bg-gold/20 text-gold px-1.5 py-0.5 rounded-sm font-semibold">
                Editor
              </span>
            ) : null}
            {m.is_top_connector ? (
              <span
                data-testid={`top-connector-badge-${m.user_id}`}
                title={`${m.approved_referrals} approved referrals`}
                className="font-mono text-[9px] uppercase tracking-wider bg-gold text-cream px-1.5 py-0.5 rounded-sm font-semibold"
              >
                Top Connector
              </span>
            ) : null}
          </div>
          {m.headline ? (
            <p
              className="font-serif text-[13px] text-ink/85 mt-1 leading-snug line-clamp-2"
              data-testid={`directory-headline-${m.user_id}`}
            >
              {m.headline}
            </p>
          ) : meta ? (
            <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink mt-1 truncate">{meta}</p>
          ) : null}
          {m.market ? (
            <p className="font-serif italic text-xs text-ink/70 mt-1">{m.market}</p>
          ) : null}
        </div>
      </div>

      {m.bio ? (
        <p className="font-serif text-sm text-ink/80 mt-3 leading-snug line-clamp-3">{m.bio}</p>
      ) : null}

      <div className="mt-3 pt-3 border-t border-gold/10 flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-ink">
          {m.essays_count > 0
            ? `${m.essays_count} ${m.essays_count === 1 ? "essay" : "essays"}`
            : "No essays yet"}
        </span>
        {m.linkedin_url ? (
          <a
            href={m.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[10px] uppercase tracking-wider text-gold hover:underline"
          >
            LinkedIn →
          </a>
        ) : null}
      </div>
    </article>
  );
}

export default function Directory() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") {
      navigate(user.status === "pending" ? "/pending" : "/join", { replace: true });
    }
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (!user || user.status !== "approved") return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await api.get("/profile/directory", { params: { q: q || undefined, limit: 120 } });
        if (!cancelled) {
          setItems(r.data.items || []);
          setCount(r.data.count || 0);
        }
      } catch (err) {
        if (!cancelled) toast.error(err?.response?.data?.detail || "Failed to load directory");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [user, q]);

  const submit = (e) => {
    e.preventDefault();
    setQ(qInput.trim());
  };

  const grouped = useMemo(() => {
    const writers = items.filter((m) => m.essays_count > 0);
    const everyone_else = items.filter((m) => m.essays_count === 0);
    return { writers, everyone_else };
  }, [items]);

  if (authLoading || !user || user.status !== "approved") {
    return <div className="container-wide py-16 font-serif italic text-muted-ink">Loading.</div>;
  }

  return (
    <div className="container-wide py-10 sm:py-14 space-y-8" data-testid="directory-page">
      <PageMeta
        title="Members"
        description="The Housing News network — a directory of real estate professionals publishing under thehousingnews.com."
      />
      <header className="space-y-3">
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">The Network</p>
        <h1 className="font-display font-semibold text-3xl sm:text-4xl ink tracking-tight">Members.</h1>
        <p className="font-serif italic text-base text-muted-ink max-w-prose">
          Everyone publishing under thehousingnews.com. {count > 0 ? `${count} approved.` : ""}
        </p>
      </header>

      <form onSubmit={submit} className="flex items-center gap-2" data-testid="directory-search-form">
        <input
          type="search"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="Search by name, market, role, or company"
          data-testid="directory-search-input"
          className="flex-1 bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <button
          type="submit"
          data-testid="directory-search-btn"
          className="font-sans text-xs uppercase tracking-wider font-semibold bg-ink text-cream px-3 py-2 rounded-sm hover:bg-gold transition-colors"
        >
          Search
        </button>
        {q ? (
          <button
            type="button"
            onClick={() => { setQ(""); setQInput(""); }}
            className="font-sans text-xs uppercase tracking-wider text-muted-ink hover:text-ink"
          >
            Clear
          </button>
        ) : null}
      </form>

      {loading && items.length === 0 ? (
        <p className="font-serif italic text-sm text-muted-ink py-12 text-center">Loading members.</p>
      ) : items.length === 0 ? (
        <div className="bg-cream-soft border border-gold/15 rounded-sm py-16 text-center" data-testid="directory-empty">
          {q ? (
            <>
              <p className="font-display font-semibold text-xl ink">No members matched "{q}".</p>
              <p className="font-serif italic text-sm text-muted-ink mt-1">Try a different search term, or invite someone new.</p>
              <Link
                to="/referrals"
                data-testid="directory-empty-invite"
                className="inline-block mt-4 font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity"
              >
                Invite a member →
              </Link>
            </>
          ) : (
            <>
              <p className="font-display font-semibold text-xl ink">The room is still small.</p>
              <p className="font-serif italic text-sm text-muted-ink mt-1 max-w-prose mx-auto">Be the start of a real-estate writing community — invite the next member.</p>
              <Link
                to="/referrals"
                data-testid="directory-empty-invite"
                className="inline-block mt-5 bg-gold text-cream font-sans text-xs uppercase tracking-wider font-semibold px-4 py-2 rounded-sm hover:opacity-90 transition-opacity"
              >
                Invite someone
              </Link>
            </>
          )}
        </div>
      ) : (
        <>
          {grouped.writers.length > 0 ? (
            <section>
              <h2 className="font-display font-semibold text-xl ink mb-4">Writers</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {grouped.writers.map((m) => <MemberCard key={m.user_id} m={m} />)}
              </div>
            </section>
          ) : null}

          {grouped.everyone_else.length > 0 ? (
            <section>
              <h2 className="font-display font-semibold text-xl ink mb-4">Members</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {grouped.everyone_else.map((m) => <MemberCard key={m.user_id} m={m} />)}
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
