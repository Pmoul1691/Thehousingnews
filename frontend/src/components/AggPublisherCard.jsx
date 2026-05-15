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

function domainOf(url) {
  if (!url) return null;
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return null; }
}

function PublisherLogo({ publisher, size = 32 }) {
  const domain = domainOf(publisher.homepage_url || publisher.feed_url);
  const fallback = (publisher.name || "?")[0].toUpperCase();
  const src = publisher.logo_url
    || (domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64` : null);
  if (!src) {
    return (
      <div
        className="flex items-center justify-center rounded-sm bg-agg-navy text-agg-cream font-display font-semibold shrink-0"
        style={{ width: size, height: size, fontSize: size * 0.45 }}
      >
        {fallback}
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={publisher.name}
      width={size}
      height={size}
      loading="lazy"
      className="rounded-sm object-contain bg-white border border-slate-100 shrink-0"
      style={{ width: size, height: size }}
      onError={(e) => {
        const span = document.createElement("span");
        span.className = "flex items-center justify-center rounded-sm bg-agg-navy text-agg-cream font-display font-semibold shrink-0";
        span.style.cssText = `width:${size}px;height:${size}px;font-size:${size * 0.45}px`;
        span.textContent = fallback;
        e.currentTarget.replaceWith(span);
      }}
    />
  );
}

/**
 * One card per publisher: logo + name + most-recent headline + "See more
 * articles" CTA to /source/{slug}. Headline opens in a new tab to the
 * publisher (never rehosted, never an internal article page).
 */
export default function AggPublisherCard({ entry }) {
  const pub = entry.publisher;
  const art = entry.article;
  return (
    <article
      data-testid={`agg-pub-card-${pub.slug}`}
      className="group flex flex-col bg-white border border-slate-200 rounded-sm hover:border-agg-orange/60 transition-colors p-5"
    >
      <header className="flex items-center gap-3 mb-3">
        <PublisherLogo publisher={pub} size={36} />
        <div className="min-w-0">
          <Link
            to={`/source/${pub.slug}`}
            data-testid={`agg-pub-card-name-${pub.slug}`}
            className="font-display font-semibold text-[15px] text-agg-navy hover:text-agg-orange transition-colors truncate block"
          >
            {pub.name}
          </Link>
          <p className="font-sans text-[10px] uppercase tracking-[0.18em] text-slate-400">
            {pub.category?.replace(/_/g, " ") || "Publisher"}
          </p>
        </div>
      </header>

      {art ? (
        <a
          href={art.original_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid={`agg-pub-card-headline-${pub.slug}`}
          className="flex-1 block group/h"
        >
          <h3 className="font-display font-semibold text-[16px] leading-snug text-agg-navy group-hover/h:text-agg-orange transition-colors">
            {art.title}
          </h3>
          <p className="font-sans text-[11px] text-slate-500 mt-1.5">
            {timeAgo(art.published_at)}
          </p>
        </a>
      ) : (
        <div className="flex-1 flex items-center text-slate-400 italic font-serif text-sm" data-testid={`agg-pub-card-empty-${pub.slug}`}>
          No items in the last 7 days.
        </div>
      )}

      <Link
        to={`/source/${pub.slug}`}
        data-testid={`agg-pub-card-more-${pub.slug}`}
        className="mt-4 inline-flex items-center justify-center self-start font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-agg-orange border border-agg-orange/40 px-3 py-1.5 rounded-sm hover:bg-agg-orange hover:text-white transition-colors"
      >
        See more articles →
      </Link>
    </article>
  );
}
