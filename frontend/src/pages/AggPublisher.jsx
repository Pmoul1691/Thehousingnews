import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import { ArticleCard } from "@/components/AggArticleCard";

const PAGE_SIZE = 30;

export default function AggPublisher() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get(`/agg/publishers/${slug}`, { params: { offset, limit: PAGE_SIZE } })
      .then((r) => { if (alive) setData(r.data); })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [slug, offset]);

  // We add a noindex meta so we don't compete with the publisher's own pages
  useEffect(() => {
    let tag = document.querySelector('meta[name="robots"]');
    const created = !tag;
    if (!tag) {
      tag = document.createElement("meta");
      tag.setAttribute("name", "robots");
      document.head.appendChild(tag);
    }
    const prev = tag.getAttribute("content");
    tag.setAttribute("content", "noindex, follow");
    return () => {
      if (created) tag.remove();
      else if (prev) tag.setAttribute("content", prev);
    };
  }, []);

  if (loading) return <p className="text-slate-500 py-12 text-center">Loading.</p>;
  if (error) return <p className="text-red-700 py-12 text-center">{error}</p>;
  if (!data?.publisher) return <p className="text-slate-700 py-12 text-center">Publisher not found.</p>;

  const p = data.publisher;
  const totalPages = Math.ceil((data.total || 0) / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div data-testid={`agg-publisher-${p.slug}`}>
      <div className="mb-6 pb-6 border-b border-slate-200">
        <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-1">{p.category.replace("_", " ")}</p>
        <h1 className="font-display font-semibold text-3xl text-agg-navy mb-2">{p.name}</h1>
        <p className="text-slate-600 text-sm max-w-prose">
          We pull the public RSS feed from <a href={p.homepage_url} target="_blank" rel="noopener noreferrer" className="text-agg-navy underline underline-offset-4 hover:text-agg-orange">{(p.homepage_url || "").replace(/^https?:\/\//, "")}</a>. Every headline below links straight back to the original article.
        </p>
        <a
          href={p.homepage_url || "#"}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="agg-publisher-subscribe-cta"
          className="inline-flex items-center mt-4 bg-agg-orange text-agg-navy font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity"
        >
          Subscribe directly to {p.name} →
        </a>
      </div>

      <h2 className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-slate-500 mb-3">Recent items</h2>
      <div className="divide-y divide-slate-200">
        {(data.items || []).map((it) => (
          <ArticleCard
            key={it.id}
            article={{
              ...it,
              publisher: { slug: p.slug, name: p.name, logo_url: p.logo_url, homepage_url: p.homepage_url },
            }}
          />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-between text-sm">
          <button
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0}
            className="font-sans text-agg-navy disabled:opacity-30 hover:text-agg-orange transition-colors"
          >
            ← Newer
          </button>
          <span className="text-slate-500">Page {currentPage} / {totalPages}</span>
          <button
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={currentPage >= totalPages}
            className="font-sans text-agg-navy disabled:opacity-30 hover:text-agg-orange transition-colors"
          >
            Older →
          </button>
        </div>
      )}
    </div>
  );
}
