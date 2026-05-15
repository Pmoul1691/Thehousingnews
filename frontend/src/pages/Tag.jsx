import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import PostItem from "@/components/PostItem";

const PAGE_SIZE = 30;

export default function Tag() {
  const { tag } = useParams();
  const tagNorm = (tag || "").toLowerCase().replace(/^#/, "");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [popular, setPopular] = useState([]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get(`/posts/by-tag/${encodeURIComponent(tagNorm)}`, { params: { limit: PAGE_SIZE } })
      .then((r) => { if (alive) { setItems(r.data.items || []); setTotal(r.data.total || 0); } })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tagNorm]);

  // Other popular tags as a sidebar / footer
  useEffect(() => {
    api.get("/posts/tags/popular", { params: { days: 30, limit: 12 } })
      .then((r) => setPopular(r.data.items || []))
      .catch(() => {});
  }, []);

  return (
    <div className="container-prose py-12" data-testid={`tag-page-${tagNorm}`}>
      <p className="uppercase-label mb-3">Tag</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-3 leading-tight">
        #{tagNorm}
      </h1>
      <p className="font-serif text-sm text-muted-ink mb-10">
        {total === 1 ? "1 post" : `${total} posts`} tagged #{tagNorm}.
      </p>

      {loading ? (
        <p className="font-serif italic text-base text-muted-ink py-16 text-center">Loading.</p>
      ) : error ? (
        <p className="font-serif text-base text-deepred py-12 text-center" data-testid="tag-page-error">{error}</p>
      ) : items.length === 0 ? (
        <div className="py-20 text-center" data-testid="tag-page-empty">
          <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">Nothing</p>
          <p className="font-serif italic text-base text-[#2C2410]/65 max-w-prose mx-auto">
            No posts tagged #{tagNorm} yet. Be the first — drop the hashtag in a post.
          </p>
        </div>
      ) : (
        <div data-testid="tag-page-results">
          {items.map((p) => <PostItem key={p.post_id} post={p} />)}
        </div>
      )}

      {popular.length > 0 && (
        <div className="mt-16 border-t hairline pt-8" data-testid="tag-page-popular">
          <p className="uppercase-label mb-3">Popular this month</p>
          <div className="flex flex-wrap gap-2">
            {popular.map((p) => (
              <Link
                key={p.tag}
                to={`/tag/${p.tag}`}
                className={`font-sans text-xs px-3 py-1 rounded-full border transition-colors ${
                  p.tag === tagNorm
                    ? "bg-gold text-cream border-gold"
                    : "hairline text-ink hover:border-gold hover:text-gold"
                }`}
              >
                #{p.tag}
                <span className="ml-1.5 text-muted-ink">{p.count}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
