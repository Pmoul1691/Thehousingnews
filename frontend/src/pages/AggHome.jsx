import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import NewsletterBand from "@/components/NewsletterBand";
import AggTrendingStrip from "@/components/AggTrendingStrip";
import DailyCard from "@/components/DailyCard";

const WINDOW_HOURS = 168;

function entryDate(e) {
  if (e.kind === "publisher") return e.article?.published_at || "";
  return e.episode?.published_at || "";
}

function compareTopics(prev, current) {
  // Cheap directional indicator: if a topic exists in current trending, mark up;
  // we don't have historical trending data so we infer from count thresholds.
  return current.map((t) => ({
    ...t,
    direction: t.count >= 4 ? "up" : t.count >= 2 ? "up" : "flat",
  }));
}

// ── Hero ──────────────────────────────────────────────────────────────────
function AggHero() {
  return (
    <section
      data-testid="agg-hero"
      className="pt-16 pb-16 sm:pt-20 sm:pb-20 border-b border-slate-200"
    >
      <p className="font-sans text-[10px] uppercase tracking-[0.28em] font-semibold text-agg-orange">
        The Daily · Housing News Network
      </p>
      <h1
        data-testid="agg-hero-headline"
        className="font-display font-semibold text-[40px] sm:text-[52px] lg:text-[60px] leading-[1.04] text-agg-navy mt-5 tracking-tight max-w-4xl"
      >
        What the housing industry is reading today.
      </h1>
      <p className="font-serif text-[17px] sm:text-[19px] leading-[1.55] text-slate-700 mt-6 max-w-3xl">
        Reporting, podcasts, and member commentary from across housing — pulled
        together in one place so you don&apos;t have to open twenty tabs to keep up.
      </p>

      <div className="flex items-center gap-6 flex-wrap mt-8">
        <Link
          to="/news/newsletter"
          data-testid="agg-hero-digest"
          className="inline-flex items-center justify-center bg-agg-orange text-white font-sans font-semibold text-sm px-6 py-2.5 rounded-sm hover:bg-agg-navy transition-colors"
        >
          Get the daily digest
        </Link>
        <a
          href="#sources"
          data-testid="agg-hero-explore"
          className="font-sans font-semibold text-sm text-agg-navy hover:text-agg-orange transition-colors"
        >
          Explore Sources →
        </a>
      </div>

      <ul className="mt-10 flex gap-10 sm:gap-14 flex-wrap" data-testid="agg-hero-stats">
        <li>
          <p className="font-display font-semibold text-[34px] text-agg-navy leading-none">40+</p>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-slate-500 mt-1">Sources</p>
        </li>
        <li>
          <p className="font-display font-semibold text-[34px] text-agg-navy leading-none">28</p>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-slate-500 mt-1">Publishers</p>
        </li>
        <li>
          <p className="font-display font-semibold text-[34px] text-agg-navy leading-none">10</p>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-slate-500 mt-1">Podcasts</p>
        </li>
      </ul>
    </section>
  );
}

// ── Philosophy strip ──────────────────────────────────────────────────────
function PhilosophyStrip() {
  return (
    <section
      data-testid="agg-philosophy"
      className="py-10 border-b border-slate-200"
    >
      <p className="font-display font-semibold text-2xl sm:text-3xl text-agg-navy tracking-tight">
        A magazine, not a feed.
      </p>
      <p className="font-serif text-base text-slate-600 italic mt-2 max-w-2xl">
        Real estate news from real publishers, plus commentary from members
        actually working in housing. No algorithm.
      </p>
    </section>
  );
}

// ── Trends visualization (uses /agg/trending) ─────────────────────────────
function TrendVisualization({ topics }) {
  if (!topics?.length) return null;
  return (
    <section
      data-testid="agg-trends"
      className="py-10 border-b border-slate-200"
    >
      <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-4">
        Trending across housing · 24h
      </p>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-12 gap-y-2">
        {topics.slice(0, 6).map((t) => (
          <li key={t.topic} className="flex items-baseline justify-between py-2 border-b border-slate-100">
            <Link
              to={`/news?topic=${encodeURIComponent(t.topic)}`}
              className="font-display text-[17px] text-agg-navy hover:text-agg-orange transition-colors truncate pr-4"
            >
              {t.topic}
            </Link>
            <span
              className={`font-sans text-sm font-semibold tabular-nums shrink-0 ${
                t.direction === "up" ? "text-emerald-700" : "text-slate-400"
              }`}
            >
              {t.direction === "up" ? "↑" : "·"} {t.count}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── Member commentary woven into the feed ──────────────────────────────────
function MemberCommentaryCard({ essay }) {
  const author = essay.author || {};
  return (
    <article
      data-testid={`agg-commentary-${essay.post_id}`}
      className="group flex flex-col bg-agg-navy text-white rounded-sm p-5 hover:bg-agg-navy-deep transition-colors"
    >
      <header className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center font-display text-white shrink-0 text-base">
          {(author.name || "M")[0]}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display font-semibold text-[15px] text-white truncate">{author.name || "Member"}</p>
          <p className="font-sans text-[10px] uppercase tracking-[0.18em] text-agg-orange font-semibold">
            Member Commentary
          </p>
        </div>
        <span className="inline-flex items-center font-sans text-[9px] uppercase tracking-[0.18em] font-semibold text-white/70 border border-white/30 px-1.5 py-0.5 rounded-sm">
          Local
        </span>
      </header>
      <Link
        to={`/essays/${essay.post_id}`}
        className="flex-1 block group/h"
      >
        <h3 className="font-display font-semibold text-[16px] leading-snug text-white group-hover/h:text-agg-orange transition-colors">
          {essay.title || "Untitled"}
        </h3>
        {author.market && (
          <p className="font-sans text-[11px] text-white/70 mt-1.5">
            {author.market}{essay.read_time_minutes ? ` · ${essay.read_time_minutes} min` : ""}
          </p>
        )}
      </Link>
      <Link
        to={`/essays/${essay.post_id}`}
        className="mt-4 inline-flex items-center self-start font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-agg-orange hover:text-white transition-colors"
      >
        Read commentary →
      </Link>
    </article>
  );
}

export default function AggHome() {
  const [pubs, setPubs] = useState([]);
  const [pods, setPods] = useState([]);
  const [essays, setEssays] = useState([]);
  const [trending, setTrending] = useState([]);
  const [loadingPubs, setLoadingPubs] = useState(true);
  const [error, setError] = useState(null);
  const [search] = useSearchParams();
  const topic = (search.get("topic") || "").trim().toLowerCase();

  useEffect(() => {
    let alive = true;
    setLoadingPubs(true);
    Promise.all([
      api.get("/agg/publishers-latest", { params: { hours: WINDOW_HOURS } }).catch(() => ({ data: { items: [] } })),
      api.get("/agg/podcasts").catch(() => ({ data: { items: [] } })),
      api.get("/essays?limit=6").catch(() => ({ data: { items: [] } })),
      api.get("/agg/trending", { params: { hours: 24, limit: 6 } }).catch(() => ({ data: { items: [] } })),
    ]).then(([pubRes, podRes, eRes, tRes]) => {
      if (!alive) return;
      setPubs(pubRes.data.items || []);
      setPods(podRes.data.items || []);
      setEssays(eRes.data.items || []);
      setTrending(compareTopics([], tRes.data.items || []));
      setLoadingPubs(false);
    }).catch((e) => {
      if (!alive) return;
      setError(e?.response?.data?.detail || "Failed to load");
      setLoadingPubs(false);
    });
    return () => { alive = false; };
  }, []);

  // Unified entries — sorted by recency, with badges assigned heuristically.
  const decorated = useMemo(() => {
    const pubEntries = pubs.map((e) => ({
      kind: "publisher",
      publisher: e.publisher,
      article: e.article,
      key: `pub:${e.publisher.id}`,
    }));
    const podEntries = pods.map((p) => ({
      kind: "podcast",
      podcast: p,
      episode: p.latest_episode,
      key: `pod:${p.id}`,
    }));
    let all = [...pubEntries, ...podEntries];
    if (topic) {
      all = all.filter((it) => {
        const title = it.kind === "publisher" ? (it.article?.title || "") : (it.episode?.title || "");
        return title.toLowerCase().includes(topic);
      });
    }
    // Sort by recency
    const withDate = all.filter((e) => entryDate(e));
    withDate.sort((a, b) => entryDate(b).localeCompare(entryDate(a)));
    // Assign badges:
    //  - position 0: Editor's Pick (gold)
    //  - oldest podcast in top 12 with most recent episode: Most Discussed
    //  - any regional publisher (slug starts with "trd-" or matches a city): Local Signal
    //  - title that includes any trending term: Trending
    const trendingTerms = trending.map((t) => t.topic).slice(0, 4);
    const result = withDate.map((e, i) => {
      let badge = null;
      const title = (e.kind === "publisher" ? e.article?.title : e.episode?.title) || "";
      const slug = e.kind === "publisher" ? e.publisher.slug : "";
      if (i === 0) {
        badge = { kind: "editors-pick", label: "Editor's Pick", cls: "bg-agg-orange/10 text-agg-orange border border-agg-orange/30" };
      } else if (e.kind === "podcast" && i < 12) {
        badge = { kind: "most-discussed", label: "Most Discussed", cls: "bg-emerald-50 text-emerald-700 border border-emerald-200" };
      } else if (/^trd-/.test(slug) || /brownstoner|curbed/.test(slug)) {
        badge = { kind: "local-signal", label: "Local", cls: "bg-amber-50 text-amber-800 border border-amber-200" };
      } else if (trendingTerms.some((tt) => title.toLowerCase().includes(tt))) {
        badge = { kind: "trending", label: "Trending", cls: "bg-emerald-50 text-emerald-700 border border-emerald-200" };
      }
      return { entry: e, badge };
    });
    return result;
  }, [pubs, pods, topic, trending]);

  const withoutLatest = useMemo(() => {
    const pubEntries = pubs.filter((e) => !e.article).map((e) => ({ kind: "publisher", publisher: e.publisher, key: `pub:${e.publisher.id}` }));
    const podEntries = pods.filter((p) => !p.latest_episode).map((p) => ({ kind: "podcast", podcast: p, key: `pod:${p.id}` }));
    return [...pubEntries, ...podEntries];
  }, [pubs, pods]);

  const loading = loadingPubs && pubs.length === 0;
  const totalSources = pubs.length + pods.length;

  if (loading) return <p className="text-slate-500 py-12 text-center" data-testid="daily-loading">Loading.</p>;
  if (error && !pubs.length) return <p className="text-red-700 py-12 text-center" data-testid="daily-error">{error}</p>;

  // Weave member commentary cards every 8 publisher/podcast cards so the
  // member voice sits inside the river, not separated from it.
  const woven = [];
  let essayIdx = 0;
  decorated.forEach((d, i) => {
    woven.push({ type: "src", ...d, key: d.entry.key });
    if ((i + 1) % 8 === 0 && essays[essayIdx]) {
      woven.push({ type: "essay", essay: essays[essayIdx], key: `essay:${essays[essayIdx].post_id}` });
      essayIdx += 1;
    }
  });

  return (
    <div data-testid="agg-home">
      <AggHero />
      <PhilosophyStrip />
      <TrendVisualization topics={trending} />
      <AggTrendingStrip />

      {topic && (
        <div className="mb-6 mt-8 flex items-center gap-3" data-testid="agg-topic-active">
          <span className="font-sans text-[11px] uppercase tracking-[0.18em] text-slate-500">Filtering</span>
          <span className="inline-flex items-center gap-2 rounded-full border border-agg-orange/40 bg-agg-orange/5 px-3 py-1 font-sans text-xs text-agg-navy">
            {topic}
            <Link to="/news" className="text-agg-orange hover:opacity-75" aria-label="Clear topic filter">✕</Link>
          </span>
          <span className="text-xs text-slate-500">{decorated.length} match{decorated.length === 1 ? "" : "es"}</span>
        </div>
      )}

      <header id="sources" className="mt-12 mb-8 flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-2">The feed</p>
          <h2 className="font-display font-semibold text-2xl sm:text-3xl text-agg-navy tracking-tight">
            What everyone is reading.
          </h2>
        </div>
        <p className="hidden sm:block text-xs text-slate-500">
          {totalSources} sources · {pubs.length} publishers · {pods.length} podcasts
        </p>
      </header>

      {decorated.length === 0 && topic ? (
        <div className="py-16 text-center border-t border-slate-100" data-testid="agg-topic-empty">
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-2">No matches</p>
          <p className="text-slate-700">No source has a recent item matching "{topic}".</p>
        </div>
      ) : (
        <section
          data-testid="daily-grid"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {woven.map((node) =>
            node.type === "essay"
              ? <MemberCommentaryCard key={node.key} essay={node.essay} />
              : <DailyCard key={node.key} entry={node.entry} badge={node.badge} />
          )}
        </section>
      )}

      {!topic && withoutLatest.length > 0 && (
        <section className="mt-12 pt-8 border-t border-slate-200" data-testid="daily-quiet">
          <h2 className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-slate-400 mb-4">
            Quiet this week
          </h2>
          <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {withoutLatest.map((entry) => {
              const slug = entry.kind === "publisher" ? entry.publisher.slug : entry.podcast.id;
              const name = entry.kind === "publisher" ? entry.publisher.name : entry.podcast.title;
              const to = entry.kind === "publisher" ? `/news/source/${slug}` : `/news/podcasts`;
              return (
                <li key={entry.key}>
                  <Link to={to} className="flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-sm hover:border-agg-orange/60 transition-colors">
                    <span className="font-sans text-[13px] text-agg-navy truncate">{name}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* "Stop searching, start understanding" closer */}
      <section data-testid="agg-closer" className="mt-20 pt-14 border-t border-slate-200">
        <div className="max-w-3xl">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-3">
            Why we built this
          </p>
          <h2 className="font-display font-semibold text-3xl sm:text-4xl text-agg-navy tracking-tight">
            One place. Twice a day. Done.
          </h2>
          <p className="font-serif text-[17px] leading-relaxed text-slate-700 mt-5">
            Most of us were following dozens of websites, newsletters, and podcasts to
            keep up with housing. The Housing News reads them for you and puts the
            day in one place — so you can read once in the morning, once in the
            evening, and get back to your clients.
          </p>
        </div>
      </section>

      <div className="mt-12">
        <NewsletterBand />
      </div>
    </div>
  );
}
