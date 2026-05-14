import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import NewsletterBand from "@/components/NewsletterBand";
import { ArticleCard, Section } from "@/components/AggArticleCard";

const HOURS = 48;
const PAGE_SIZE = 50;

function groupByHour(items) {
  const groups = new Map();
  for (const it of items) {
    const dt = new Date(it.published_at);
    const key = `${dt.getFullYear()}-${dt.getMonth() + 1}-${dt.getDate()}-${dt.getHours()}`;
    if (!groups.has(key)) {
      groups.set(key, { key, when: dt, items: [] });
    }
    groups.get(key).items.push(it);
  }
  return Array.from(groups.values()).sort((a, b) => b.when - a.when);
}

function formatHour(d) {
  const now = new Date();
  const sameDay = now.toDateString() === d.toDateString();
  const opts = sameDay
    ? { hour: "numeric", minute: "2-digit" }
    : { weekday: "short", hour: "numeric", minute: "2-digit" };
  return new Intl.DateTimeFormat("en-US", opts).format(d);
}

export default function AggHome() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get("/agg/articles", { params: { hours: HOURS, limit: PAGE_SIZE } })
      .then((r) => { if (alive) setItems(r.data.items || []); })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) return <p className="text-slate-500 py-12 text-center">Loading the river.</p>;
  if (error) return <p className="text-red-700 py-12 text-center" data-testid="agg-home-error">{error}</p>;
  if (!items.length) {
    return (
      <div className="py-20 text-center" data-testid="agg-home-empty">
        <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-2">Nothing yet</p>
        <p className="text-slate-700">No items in the last {HOURS} hours. The next pull runs every 15 minutes.</p>
      </div>
    );
  }

  const groups = groupByHour(items);

  return (
    <div data-testid="agg-home">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-display font-semibold text-2xl sm:text-3xl text-agg-navy">The river.</h1>
          <p className="text-sm text-slate-500 mt-1">Last {HOURS} hours. Newest first. Click any headline to read at the publisher.</p>
        </div>
        <p className="hidden sm:block text-xs text-slate-500">{items.length} items</p>
      </div>

      {groups.map((g, gi) => {
        const cards = [];
        g.items.forEach((it, ii) => {
          cards.push(<ArticleCard key={it.id} article={it} />);
          // Newsletter band every 15 items, global counter
          const globalIdx = groups.slice(0, gi).reduce((acc, gg) => acc + gg.items.length, 0) + ii + 1;
          if (globalIdx % 15 === 0 && globalIdx < items.length) {
            cards.push(<NewsletterBand key={`nb-${globalIdx}`} compact />);
          }
        });
        return (
          <Section key={g.key} label={formatHour(g.when)} testid={`agg-hour-${g.key}`}>
            {cards}
          </Section>
        );
      })}

      <NewsletterBand />
    </div>
  );
}
