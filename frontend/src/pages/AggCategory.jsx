import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import NewsletterBand from "@/components/NewsletterBand";
import { ArticleCard, Section } from "@/components/AggArticleCard";

const HOURS = 96; // category pages show a wider window
const PAGE_SIZE = 50;

const CATEGORY_LABELS = {
  national_trade: "National trade",
  regional: "Regional",
  industry_blog: "Industry blogs",
  data_research: "Data & research",
  mortgage: "Mortgage",
  commercial_re: "Commercial",
  community_discussion: "Community discussion",
};

function dayKey(d) {
  return new Intl.DateTimeFormat("en-US", { weekday: "long", month: "short", day: "numeric" }).format(d);
}

export default function AggCategory() {
  const { category } = useParams();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get("/agg/articles", { params: { category, hours: HOURS, limit: PAGE_SIZE } })
      .then((r) => { if (alive) setItems(r.data.items || []); })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [category]);

  const label = CATEGORY_LABELS[category] || category;
  if (loading) return <p className="text-slate-500 py-12 text-center">Loading.</p>;
  if (error) return <p className="text-red-700 py-12 text-center">{error}</p>;

  // Group by day for category pages (wider window)
  const groups = new Map();
  for (const it of items) {
    const d = new Date(it.published_at);
    const k = d.toDateString();
    if (!groups.has(k)) groups.set(k, { key: k, when: d, items: [] });
    groups.get(k).items.push(it);
  }
  const ordered = Array.from(groups.values()).sort((a, b) => b.when - a.when);

  return (
    <div data-testid={`agg-category-${category}`}>
      <div className="mb-6">
        <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-1">Category</p>
        <h1 className="font-display font-semibold text-3xl text-agg-navy">{label}</h1>
        <p className="text-sm text-slate-500 mt-1">Last {HOURS / 24} days.</p>
      </div>

      {ordered.length === 0 ? (
        <p data-testid="agg-category-empty" className="text-slate-700 py-12 text-center">No items in the window.</p>
      ) : ordered.map((g) => (
        <Section key={g.key} label={dayKey(g.when)} testid={`agg-day-${g.key}`}>
          {g.items.map((it) => <ArticleCard key={it.id} article={it} />)}
        </Section>
      ))}

      <NewsletterBand />
    </div>
  );
}
