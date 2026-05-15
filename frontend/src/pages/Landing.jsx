import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { FeaturedEssay, EssayMini } from "@/components/EssayCards";

const signIn = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + "/auth/callback";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

function formatWhen(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "America/Chicago" }).format(new Date(iso));
  } catch { return ""; }
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function ShortPostRow({ post }) {
  const author = post.author || {};
  return (
    <article data-testid={`landing-post-${post.post_id}`} className="py-7">
      <div className="font-sans text-xs text-muted-ink mb-3">
        <span className="ink font-medium">{author.name || "Member"}</span>
        {author.market ? ` · ${author.market}` : ""}
        {" · "}{formatWhen(post.release_at || post.created_at)}
      </div>
      {post.text && (
        <p className="prose-serif text-[17px] leading-[1.72] ink whitespace-pre-wrap line-clamp-4 max-w-prose">
          {post.text}
        </p>
      )}
    </article>
  );
}

function DailyHeadlineRow({ entry, index }) {
  const isPublisher = entry.kind !== "podcast";
  const source = isPublisher ? entry.publisher : entry.podcast;
  const item = isPublisher ? entry.article : entry.episode;
  const sourceName = isPublisher ? source.name : source.title;
  const href = isPublisher ? item?.original_url : (item?.link || source.apple_url);

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      data-testid={`landing-daily-${index}`}
      className="group flex items-start gap-4 py-4 border-b border-[#E8D4A0]/40 last:border-b-0 hover:bg-[#F5EDD6]/30 -mx-3 px-3 transition-colors"
    >
      <span
        className="font-display font-semibold text-2xl text-gold/40 tabular-nums shrink-0 mt-0.5 w-6 text-right"
        aria-hidden="true"
      >
        {index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="font-sans text-[10px] uppercase tracking-[0.16em] font-semibold text-gold truncate max-w-[180px]">
            {sourceName}
          </span>
          {!isPublisher && (
            <span className="font-sans text-[9px] uppercase tracking-[0.18em] font-semibold text-deepred/80 bg-deepred/5 px-1.5 py-0.5 rounded-sm">
              Podcast
            </span>
          )}
          <span className="font-sans text-[11px] text-muted-ink ml-auto shrink-0">{timeAgo(item?.published_at)}</span>
        </div>
        <p className="font-display text-[15px] leading-snug ink group-hover:text-gold transition-colors line-clamp-2">
          {item?.title}
        </p>
      </div>
    </a>
  );
}

function TheDailyPanel() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get("/agg/publishers-latest", { params: { hours: 24 } }).catch(() => ({ data: { items: [] } })),
      api.get("/agg/podcasts").catch(() => ({ data: { items: [] } })),
    ]).then(([pubRes, podRes]) => {
      if (!alive) return;
      const pubs = (pubRes.data.items || [])
        .filter((e) => e.article)
        .map((e) => ({ kind: "publisher", publisher: e.publisher, article: e.article }));
      const pods = (podRes.data.items || [])
        .filter((p) => p.latest_episode)
        .map((p) => ({ kind: "podcast", podcast: p, episode: p.latest_episode }));
      const merged = [...pubs, ...pods]
        .sort((a, b) => {
          const ad = (a.article || a.episode).published_at || "";
          const bd = (b.article || b.episode).published_at || "";
          return bd.localeCompare(ad);
        })
        .slice(0, 6);
      setEntries(merged);
      setLoading(false);
    });
    return () => { alive = false; };
  }, []);

  return (
    <aside
      data-testid="landing-daily-panel"
      className="relative bg-[#FBF6E8] border hairline rounded-sm p-8 sm:p-9 lg:sticky lg:top-24"
    >
      <div className="flex items-baseline justify-between mb-7 pb-5 border-b hairline">
        <div>
          <p className="font-sans text-[10px] uppercase tracking-[0.28em] font-semibold text-gold">
            The Daily · Free
          </p>
          <h2 className="font-display font-semibold text-2xl ink mt-2 leading-tight">
            What we're reading today.
          </h2>
        </div>
      </div>

      <p className="font-serif italic text-[14px] text-muted-ink leading-relaxed mb-6">
        Real-time aggregator of 28 real estate publishers and 10 podcasts. Free, no signup, no paywalls.
      </p>

      {loading ? (
        <div className="py-12 text-center">
          <p className="font-serif italic text-sm text-muted-ink">Loading.</p>
        </div>
      ) : entries.length === 0 ? (
        <div className="py-8 text-center">
          <p className="font-serif italic text-sm text-muted-ink">No items in the last 24 hours.</p>
        </div>
      ) : (
        <div className="mb-7">
          {entries.map((e, i) => (
            <DailyHeadlineRow
              key={e.kind === "publisher" ? `p${e.publisher.id}` : `pod${e.podcast.id}`}
              entry={e}
              index={i}
            />
          ))}
        </div>
      )}

      <Link
        to="/news"
        data-testid="landing-daily-more"
        className="inline-flex items-center justify-center w-full bg-ink text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:bg-gold transition-colors"
        style={{ backgroundColor: "#2C2410" }}
      >
        Open The Daily →
      </Link>
    </aside>
  );
}

export default function Landing() {
  const [essays, setEssays] = useState([]);
  const [shorts, setShorts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [pubRes, essaysRes] = await Promise.all([
          api.get("/posts/public?limit=30"),
          api.get("/essays?limit=8"),
        ]);
        if (!alive) return;
        const items = pubRes.data.items || [];
        setShorts(items.filter((p) => (p.kind || "post") !== "essay").slice(0, 5));
        setEssays(essaysRes.data.items || []);
      } catch (_e) {
        // public endpoints; ignore
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const featured = essays[0];
  const restEssays = essays.slice(1, 6);

  return (
    <div data-testid="landing-page" className="bg-cream">
      {/* === Split hero: Magazine | The Daily === */}
      <section className="container-wide pt-12 sm:pt-16 pb-16 animate-fade-up" data-testid="landing-split-hero">
        <div className="grid grid-cols-1 lg:grid-cols-[1.05fr_1px_0.95fr] gap-10 lg:gap-0 items-start">
          {/* LEFT — The Magazine */}
          <div className="lg:pr-12">
            <p className="font-sans text-[11px] uppercase tracking-[0.28em] font-semibold text-gold mb-7" data-testid="landing-eyebrow">
              The Magazine · Members
            </p>
            <h1
              data-testid="landing-headline"
              className="font-display font-semibold tracking-tight text-4xl sm:text-5xl lg:text-6xl ink leading-[0.98] mb-6"
            >
              A daily magazine
              <br />
              for the real estate
              <br />
              industry.
            </h1>
            <p className="font-serif italic text-base sm:text-lg text-[#2C2410]/70 leading-relaxed max-w-prose mb-8">
              Written by people who close deals. Released twice a day, at 8:30am and 5:30pm.
            </p>
            <div className="flex items-center gap-5 flex-wrap mb-10">
              <Link
                to="/apply"
                data-testid="landing-apply-btn"
                className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-2.5 rounded-full hover:opacity-90 transition-opacity"
              >
                Apply for membership
              </Link>
              <button
                onClick={signIn}
                data-testid="landing-signin-btn"
                className="font-sans text-sm font-medium ink hover:text-gold transition-colors"
              >
                Sign in
              </button>
              <Link
                to="/about"
                data-testid="landing-about-link"
                className="font-sans text-sm font-medium ink hover:text-gold transition-colors"
              >
                About
              </Link>
            </div>

            {/* Quiet teaser of latest essay so the left side has visual weight */}
            {featured && (
              <Link
                to={`/essays/${featured.post_id}`}
                data-testid="landing-featured-teaser"
                className="block border-t hairline pt-7 group"
              >
                <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">
                  Latest essay
                </p>
                <h3 className="font-display font-semibold text-xl sm:text-2xl ink group-hover:text-gold transition-colors leading-snug mb-2">
                  {featured.title || "Untitled"}
                </h3>
                {featured.author?.name && (
                  <p className="font-sans text-xs text-muted-ink">
                    {featured.author.name}{featured.author.market ? ` · ${featured.author.market}` : ""}
                    {" · "}{formatWhen(featured.release_at || featured.created_at)}
                  </p>
                )}
              </Link>
            )}
          </div>

          {/* CENTER — Vertical hairline divider on desktop only */}
          <div className="hidden lg:block w-px bg-gradient-to-b from-transparent via-gold/30 to-transparent self-stretch" aria-hidden="true" />

          {/* RIGHT — The Daily */}
          <div className="lg:pl-12">
            <TheDailyPanel />
          </div>
        </div>
      </section>

      {/* More essays + member voices, unchanged from before but lighter weight */}
      {restEssays.length > 0 && (
        <>
          <div className="container-prose">
            <div className="border-t hairline" />
          </div>
          <section className="container-prose py-14" data-testid="landing-magazine-list">
            <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">
              More essays
            </p>
            <div className="divide-y divide-[#E8D4A0]/60">
              {restEssays.map((e) => (
                <EssayMini
                  key={e.post_id}
                  essay={e}
                  variant="row"
                  linkTo={`/essays/${e.post_id}`}
                  testIdPrefix="landing-mini"
                />
              ))}
            </div>
          </section>
        </>
      )}

      {shorts.length > 0 && (
        <>
          <div className="container-prose">
            <div className="border-t hairline" />
          </div>
          <section className="container-prose py-14" data-testid="landing-shorts">
            <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">
              From the feed
            </p>
            <div className="divide-y divide-[#E8D4A0]/60">
              {shorts.map((p) => <ShortPostRow key={p.post_id} post={p} />)}
            </div>
          </section>
        </>
      )}

      {!loading && !featured && shorts.length === 0 && (
        <section className="container-prose py-24 text-center" data-testid="landing-empty">
          <p className="font-serif italic text-base text-muted-ink">No posts in the last two weeks. Check back at the next release window.</p>
        </section>
      )}

      <div className="container-prose">
        <div className="border-t hairline" />
      </div>
      <section className="container-prose py-20 text-center">
        <h2 className="font-display font-semibold text-2xl sm:text-3xl ink leading-tight mb-4">
          A small newsroom, on purpose.
        </h2>
        <p className="font-serif italic text-base text-[#2C2410]/65 leading-relaxed max-w-prose mx-auto mb-8">
          The editors read every application.
        </p>
        <button
          onClick={signIn}
          data-testid="footer-signin-btn"
          className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-2.5 rounded-full hover:opacity-90 transition-opacity"
        >
          Sign in
        </button>
      </section>
    </div>
  );
}
