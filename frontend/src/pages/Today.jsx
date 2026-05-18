import React, { useEffect, useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

/**
 * The "Today" home — the post-login landing page for approved members.
 *
 * Hooks every login into either a read action or a write action:
 *   • Today's briefing (the daily ritual)
 *   • Recent member essays (the network is alive)
 *   • Top 4 aggregator stories (the industry pulse)
 *   • Their in-progress draft (or a write prompt if none)
 *   • Inline notifications (replies + new followers)
 */

function Greeting({ name }) {
  const hour = new Date().getHours();
  const part = hour < 5 ? "evening" : hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
  const first = (name || "").split(" ")[0] || "there";
  return (
    <h1 data-testid="today-greeting" className="font-display font-semibold text-3xl sm:text-4xl ink tracking-tight">
      Good {part}, {first}.
    </h1>
  );
}

function NotificationStrip({ n }) {
  const total = (n?.new_replies || 0) + (n?.new_followers || 0);
  if (total === 0) return null;
  const parts = [];
  if (n.new_replies > 0) parts.push(`${n.new_replies} new ${n.new_replies === 1 ? "reply" : "replies"}`);
  if (n.new_followers > 0) parts.push(`${n.new_followers} new ${n.new_followers === 1 ? "follower" : "followers"}`);
  return (
    <div
      data-testid="today-notifications"
      className="bg-gold/10 border border-gold/30 rounded-sm px-4 py-2.5 flex items-center justify-between gap-3"
    >
      <p className="font-sans text-sm ink">
        <span className="font-semibold text-gold uppercase tracking-wider text-[11px] mr-2">New</span>
        {parts.join(" · ")} since you last visited.
      </p>
      <Link to="/profile" className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:underline whitespace-nowrap">
        View →
      </Link>
    </div>
  );
}

function BriefingArticle({ a, idx }) {
  const pub = a.publisher || {};
  return (
    <li data-testid={`briefing-article-${idx}`} className="flex items-baseline gap-3 py-2.5 border-b border-gold/10 last:border-0">
      <span className="font-mono text-[10px] text-muted-ink shrink-0 w-5">{(idx + 1).toString().padStart(2, "0")}</span>
      <div className="flex-1 min-w-0">
        <a
          href={a.original_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-display font-semibold text-[15px] ink hover:text-gold leading-snug block"
        >
          {a.title}
        </a>
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink mt-0.5">
          {pub.name || "Source"}
        </p>
      </div>
    </li>
  );
}

function BriefingCard({ briefing }) {
  if (!briefing || !briefing.articles?.length) return null;
  const label = briefing.kind === "morning" ? "Morning Brief" : "Evening Brief";
  return (
    <section data-testid="today-briefing" className="bg-cream-soft border border-gold/15 rounded-sm p-5 sm:p-6">
      <div className="flex items-baseline justify-between gap-3 mb-4">
        <div>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">{label}</p>
          <h2 className="font-display font-semibold text-2xl ink mt-1 tracking-tight">What you need to know today.</h2>
        </div>
        <Link to="/news/latest" className="hidden sm:inline font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:underline shrink-0">
          Full feed →
        </Link>
      </div>
      <ol className="list-none">
        {briefing.articles.slice(0, 6).map((a, i) => (
          <BriefingArticle key={a.id || i} a={a} idx={i} />
        ))}
      </ol>
      {briefing.trending && briefing.trending.length > 0 && (
        <div className="mt-5 pt-4 border-t border-gold/10">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-2">Trending · 24h</p>
          <div className="flex flex-wrap gap-2">
            {briefing.trending.slice(0, 6).map((t, i) => (
              <span key={i} data-testid={`today-trending-${i}`} className="font-mono text-[11px] bg-white border border-gold/20 rounded-sm px-2 py-1 text-ink/80">
                {typeof t === "string" ? t : (t.topic || t.term || t.word || t.label || "")}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function RecentEssays({ essays }) {
  if (!essays?.length) {
    return (
      <section data-testid="today-essays-empty" className="bg-white border border-gold/15 rounded-sm p-5">
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">From members</p>
        <p className="font-serif italic text-sm text-muted-ink mt-3">
          No essays yet — you could be the first to publish.{" "}
          <Link to="/write" className="text-gold hover:underline font-semibold not-italic">Start one →</Link>
        </p>
      </section>
    );
  }
  return (
    <section data-testid="today-essays" className="bg-white border border-gold/15 rounded-sm p-5">
      <div className="flex items-baseline justify-between mb-4">
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">From members</p>
        <Link to="/essays" className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold hover:underline">
          All essays →
        </Link>
      </div>
      <ol className="space-y-4">
        {essays.map((e) => {
          const author = e.author || {};
          return (
            <li key={e.post_id} data-testid={`today-essay-${e.post_id}`} className="border-b border-gold/10 last:border-0 pb-4 last:pb-0">
              <Link to={`/essays/${e.post_id}`} className="block group">
                <h3 className="font-display font-semibold text-[17px] ink leading-snug group-hover:text-gold transition-colors">
                  {e.title || "(untitled)"}
                </h3>
                {e.subtitle && (
                  <p className="font-serif text-[14px] text-ink/70 mt-1 leading-snug line-clamp-2">{e.subtitle}</p>
                )}
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink mt-1.5">
                  {author.name || "—"}
                  {author.market ? ` · ${author.market}` : ""}
                  {e.read_time_minutes ? ` · ${e.read_time_minutes} min` : ""}
                </p>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function TopAggregator({ items }) {
  if (!items?.length) return null;
  return (
    <section data-testid="today-aggregator" className="bg-white border border-gold/15 rounded-sm p-5">
      <div className="flex items-baseline justify-between mb-4">
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">What everyone is reading</p>
        <Link to="/news/latest" className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold hover:underline">
          All sources →
        </Link>
      </div>
      <ol className="space-y-3.5">
        {items.map((a, i) => {
          const pub = a.publisher || {};
          return (
            <li key={a.id || i} data-testid={`today-agg-${i}`}>
              <a href={a.original_url} target="_blank" rel="noopener noreferrer" className="block group">
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink mb-0.5">
                  {pub.name || "Source"}
                </p>
                <h3 className="font-display font-semibold text-[15px] ink leading-snug group-hover:text-gold transition-colors line-clamp-2">
                  {a.title}
                </h3>
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function WriteNudge({ draft }) {
  const hasDraft = draft && (draft.text || draft.title);
  return (
    <section
      data-testid="today-write-nudge"
      className="bg-ink text-cream border border-ink rounded-sm p-5 sm:p-6"
    >
      <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">
        {hasDraft ? "Pick up where you left off" : "Your turn"}
      </p>
      {hasDraft ? (
        <>
          <h2 className="font-display font-semibold text-xl mt-2 leading-snug line-clamp-2">
            {draft.title || draft.text?.slice(0, 80) || "Untitled draft"}
          </h2>
          <p className="font-serif text-[13px] text-cream/70 mt-2">
            Last edited {draft.updated_at ? new Date(draft.updated_at).toLocaleString() : "recently"}.
          </p>
          <Link
            to="/write"
            data-testid="today-resume-draft"
            className="inline-flex items-center bg-gold text-ink font-sans font-semibold text-sm px-4 py-2 rounded-sm mt-4 hover:bg-cream transition-colors"
          >
            Continue writing →
          </Link>
        </>
      ) : (
        <>
          <h2 className="font-display font-semibold text-2xl mt-2 leading-snug">
            Publish what you&apos;re seeing this week.
          </h2>
          <p className="font-serif text-[14px] text-cream/75 mt-2 max-w-prose">
            One deal, one trend, one note from the street. Members are looking for the texture only you can give.
          </p>
          <Link
            to="/write"
            data-testid="today-start-writing"
            className="inline-flex items-center bg-gold text-ink font-sans font-semibold text-sm px-4 py-2 rounded-sm mt-4 hover:bg-cream transition-colors"
          >
            Start writing →
          </Link>
        </>
      )}
    </section>
  );
}

export default function Today() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Send unauthenticated / unapproved users back to the landing page
  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") {
      // route them to the right step in the funnel
      if (user.status === "pending") navigate("/pending", { replace: true });
      else if (user.status === "declined") navigate("/declined", { replace: true });
      else navigate("/apply", { replace: true });
    }
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (!user || user.status !== "approved") return;
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get("/today");
        if (!cancelled) setData(r.data);
      } catch (err) {
        if (!cancelled) toast.error(err?.response?.data?.detail || "Failed to load Today");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const viewerName = useMemo(() => data?.viewer?.name || user?.name || "", [data, user]);

  if (authLoading || !user || user.status !== "approved") {
    return <div className="container-wide py-16 font-serif italic text-muted-ink">Loading.</div>;
  }
  if (loading) {
    return <div className="container-wide py-16 font-serif italic text-muted-ink" data-testid="today-loading">Loading today.</div>;
  }
  if (!data) {
    return <div className="container-wide py-16 font-serif italic text-muted-ink">Couldn&apos;t load today.</div>;
  }

  return (
    <div className="container-wide py-10 sm:py-14 space-y-6" data-testid="today-page">
      <header className="space-y-3">
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Today · {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</p>
        <Greeting name={viewerName} />
      </header>

      <NotificationStrip n={data.notifications} />

      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-6 items-start">
        <div className="space-y-6">
          <BriefingCard briefing={data.briefing} />
          <WriteNudge draft={data.my_draft} />
        </div>
        <div className="space-y-6">
          <RecentEssays essays={data.recent_essays} />
          <TopAggregator items={data.top_aggregator} />
        </div>
      </div>
    </div>
  );
}
