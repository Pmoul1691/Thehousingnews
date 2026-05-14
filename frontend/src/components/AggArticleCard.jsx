import React from "react";
import { Link } from "react-router-dom";

function timeAgo(iso) {
  if (!iso) return "";
  const now = new Date();
  const then = new Date(iso);
  const diff = (now - then) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function Section({ label, testid, children }) {
  return (
    <section data-testid={testid} className="mb-8">
      <h2 className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-3 sticky top-[78px] sm:top-[82px] z-10 bg-white py-2 -mx-4 px-4 sm:-mx-6 sm:px-6">
        {label}
      </h2>
      <div className="divide-y divide-slate-200">{children}</div>
    </section>
  );
}

/**
 * Single-item card. Hard rules:
 * - Headline links to original_url (target=_blank, rel=noopener noreferrer).
 * - Publisher name links to /source/[slug].
 * - Thumbnail uses publisher's URL only — never rehosted.
 * - Snippet appears ONLY if present (server caps at 280 chars / 2 sentences).
 */
export function ArticleCard({ article }) {
  const pub = article.publisher || {};
  return (
    <article data-testid={`agg-article-${article.id}`} className="py-4 first:pt-0 last:pb-0">
      <div className="flex gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            {pub.logo_url ? (
              <img src={pub.logo_url} alt="" className="w-4 h-4 object-contain rounded-sm" />
            ) : null}
            <Link
              to={`/source/${pub.slug}`}
              data-testid={`agg-article-publisher-${article.id}`}
              className="font-sans text-[12px] font-semibold text-agg-navy hover:text-agg-orange transition-colors"
            >
              {pub.name || "Publisher"}
            </Link>
            <span className="text-slate-400 text-[11px]">·</span>
            <span className="text-slate-500 text-[11px]">{timeAgo(article.published_at)}</span>
          </div>
          <h3 className="font-display font-semibold text-[17px] sm:text-[18px] leading-snug text-agg-navy">
            <a
              href={article.original_url}
              target="_blank"
              rel="noopener noreferrer"
              data-testid={`agg-article-headline-${article.id}`}
              className="hover:text-agg-orange transition-colors"
            >
              {article.title}
            </a>
          </h3>
          {article.snippet && (
            <p className="font-serif text-[14px] text-slate-700 leading-relaxed mt-1.5">{article.snippet}</p>
          )}
        </div>
        {article.thumbnail_url && (
          <a
            href={article.original_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`agg-article-thumb-${article.id}`}
            className="shrink-0"
          >
            <img
              src={article.thumbnail_url}
              alt=""
              className="w-20 h-20 sm:w-24 sm:h-24 object-cover rounded-sm bg-slate-100"
              loading="lazy"
              onError={(e) => { e.currentTarget.style.display = "none"; }}
            />
          </a>
        )}
      </div>
    </article>
  );
}
