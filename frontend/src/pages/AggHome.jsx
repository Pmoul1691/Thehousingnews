import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import NewsletterBand from "@/components/NewsletterBand";
import AggTrendingStrip from "@/components/AggTrendingStrip";
import AggPublisherCard from "@/components/AggPublisherCard";

const WINDOW_HOURS = 168;

export default function AggHome() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search] = useSearchParams();
  const topic = (search.get("topic") || "").trim().toLowerCase();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get("/agg/publishers-latest", { params: { hours: WINDOW_HOURS } })
      .then((r) => { if (alive) setItems(r.data.items || []); })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  // When a trending chip is active we filter the publisher cards to only
  // those whose latest headline matches the topic substring.
  const filtered = useMemo(() => {
    if (!topic) return items;
    return items.filter((it) =>
      (it.article?.title || "").toLowerCase().includes(topic)
    );
  }, [items, topic]);

  if (loading) return <p className="text-slate-500 py-12 text-center">Loading.</p>;
  if (error) return <p className="text-red-700 py-12 text-center" data-testid="agg-home-error">{error}</p>;

  const withArticles = filtered.filter((it) => it.article);
  const withoutArticles = filtered.filter((it) => !it.article);
  const totalActive = items.length;

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
          <span className="text-xs text-slate-500">{withArticles.length} publisher{withArticles.length === 1 ? "" : "s"} match</span>
        </div>
      )}

      <header className="mb-8 flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="font-display font-semibold text-2xl sm:text-3xl text-agg-navy">
            Every publisher we follow.
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {totalActive} sources. Latest headline from each. Click through to read at the publisher.
          </p>
        </div>
        <Link
          to="/news/newsletter"
          className="hidden sm:inline-flex font-sans text-xs uppercase tracking-[0.18em] font-semibold text-agg-orange hover:opacity-80"
        >
          Get the daily digest →
        </Link>
      </header>

      {withArticles.length === 0 && topic ? (
        <div className="py-16 text-center border-t border-slate-100" data-testid="agg-topic-empty">
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-2">No matches</p>
          <p className="text-slate-700">No publisher has a recent headline matching "{topic}".</p>
        </div>
      ) : (
        <section
          data-testid="agg-publisher-grid"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {withArticles.map((entry) => (
            <AggPublisherCard key={entry.publisher.id} entry={entry} />
          ))}
        </section>
      )}

      {!topic && withoutArticles.length > 0 && (
        <section className="mt-12 pt-8 border-t border-slate-200" data-testid="agg-publisher-quiet">
          <h2 className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-slate-400 mb-4">
            Quiet this week
          </h2>
          <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {withoutArticles.map((entry) => (
              <li key={entry.publisher.id}>
                <Link
                  to={`/news/source/${entry.publisher.slug}`}
                  className="flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-sm hover:border-agg-orange/60 transition-colors"
                >
                  <span className="font-sans text-[13px] text-agg-navy truncate">{entry.publisher.name}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mt-12">
        <NewsletterBand />
      </div>
    </div>
  );
}
