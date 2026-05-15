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

export default function AggHome() {
  const [pubs, setPubs] = useState([]);
  const [pods, setPods] = useState([]);
  const [loadingPubs, setLoadingPubs] = useState(true);
  const [loadingPods, setLoadingPods] = useState(true);
  const [error, setError] = useState(null);
  const [search] = useSearchParams();
  const topic = (search.get("topic") || "").trim().toLowerCase();

  useEffect(() => {
    let alive = true;
    setLoadingPubs(true);
    api
      .get("/agg/publishers-latest", { params: { hours: WINDOW_HOURS } })
      .then((r) => { if (alive) setPubs(r.data.items || []); })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoadingPubs(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    setLoadingPods(true);
    api
      .get("/agg/podcasts")
      .then((r) => { if (alive) setPods(r.data.items || []); })
      .catch(() => {})  // podcast failures shouldn't break the page
      .finally(() => { if (alive) setLoadingPods(false); });
    return () => { alive = false; };
  }, []);

  // Build unified entry list. Publishers + podcasts share the same card
  // shape; both carry a published_at timestamp on their "latest" item so we
  // can sort them together. Entries without a latest item fall to the bottom.
  const entries = useMemo(() => {
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
    return [...pubEntries, ...podEntries];
  }, [pubs, pods]);

  const filtered = useMemo(() => {
    if (!topic) return entries;
    return entries.filter((it) => {
      const title = it.kind === "publisher"
        ? (it.article?.title || "")
        : (it.episode?.title || "");
      return title.toLowerCase().includes(topic);
    });
  }, [entries, topic]);

  const withLatest = filtered.filter((e) => entryDate(e));
  withLatest.sort((a, b) => entryDate(b).localeCompare(entryDate(a)));
  const withoutLatest = filtered.filter((e) => !entryDate(e));

  const loading = loadingPubs && pubs.length === 0;
  const totalSources = pubs.length + pods.length;

  if (loading) return <p className="text-slate-500 py-12 text-center" data-testid="daily-loading">Loading.</p>;
  if (error && !pubs.length) return <p className="text-red-700 py-12 text-center" data-testid="daily-error">{error}</p>;

  return (
    <div data-testid="agg-home">
      <AggTrendingStrip />

      {topic && (
        <div className="mb-6 flex items-center gap-3" data-testid="agg-topic-active">
          <span className="font-sans text-[11px] uppercase tracking-[0.18em] text-slate-500">Filtering</span>
          <span className="inline-flex items-center gap-2 rounded-full border border-agg-orange/40 bg-agg-orange/5 px-3 py-1 font-sans text-xs text-agg-navy">
            {topic}
            <Link to="/news" className="text-agg-orange hover:opacity-75" aria-label="Clear topic filter">✕</Link>
          </span>
          <span className="text-xs text-slate-500">{withLatest.length} match{withLatest.length === 1 ? "" : "es"}</span>
        </div>
      )}

      <header className="mb-8 flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="font-display font-semibold text-2xl sm:text-3xl text-agg-navy" data-testid="daily-title">
            The Daily.
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {totalSources} sources — {pubs.length} publishers and {pods.length} podcasts. Latest from each. Click through to read or listen.
          </p>
        </div>
        <Link
          to="/news/newsletter"
          className="hidden sm:inline-flex font-sans text-xs uppercase tracking-[0.18em] font-semibold text-agg-orange hover:opacity-80"
        >
          Get the daily digest →
        </Link>
      </header>

      {withLatest.length === 0 && topic ? (
        <div className="py-16 text-center border-t border-slate-100" data-testid="agg-topic-empty">
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-2">No matches</p>
          <p className="text-slate-700">No source has a recent item matching "{topic}".</p>
        </div>
      ) : (
        <section
          data-testid="daily-grid"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {withLatest.map((entry) => (
            <DailyCard key={entry.key} entry={entry} />
          ))}
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
              const to = entry.kind === "publisher"
                ? `/news/source/${slug}`
                : `/news/podcasts`;
              return (
                <li key={entry.key}>
                  <Link
                    to={to}
                    className="flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-sm hover:border-agg-orange/60 transition-colors"
                  >
                    <span className="font-sans text-[13px] text-agg-navy truncate">{name}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="mt-12">
        <NewsletterBand />
      </div>
    </div>
  );
}
