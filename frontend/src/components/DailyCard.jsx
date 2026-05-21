import React from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";

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

function MarkLogo({ name, src, size = 40 }) {
  const fallback = (name || "?")[0].toUpperCase();
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
      alt={name}
      width={size}
      height={size}
      loading="lazy"
      className="rounded-sm object-cover bg-white border border-slate-100 shrink-0"
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
 * Unified card for "The Daily" — one shape for both publisher entries and
 * podcast entries. Each card shows: source mark + name, eyebrow label, the
 * latest title, a relative timestamp, and a CTA button that links to the
 * source's archive page on our site (for publishers) or to the latest
 * episode page (for podcasts).
 *
 * The `entry` prop is the union of:
 *   - { kind: "publisher", publisher: {...}, article: {...} | null }
 *   - { kind: "podcast",   podcast: {...},   episode: {...} | null }
 */
export default function DailyCard({ entry, badge, isHottest }) {
  // Fire a non-blocking click tracker before letting the browser open the
  // publisher's site. Failures are swallowed — analytics never blocks UX.
  const trackArticleClick = (articleId) => {
    if (!articleId) return;
    try {
      let sid = null;
      try { sid = sessionStorage.getItem("thn_event_session"); } catch { /* ignore */ }
      api.post(`/agg/articles/${encodeURIComponent(articleId)}/click`, { session_id: sid }).catch(() => {});
    } catch { /* never block UX */ }
  };

  const BadgeChip = badge ? (
    <span
      data-testid={`daily-card-badge-${badge.kind}`}
      className={`inline-flex items-center gap-1 font-sans text-[9px] uppercase tracking-[0.18em] font-semibold px-1.5 py-0.5 rounded-sm ${badge.cls}`}
    >
      {badge.label}
    </span>
  ) : null;

  if (entry.kind === "podcast") {
    const pod = entry.podcast;
    const ep = entry.episode;
    return (
      <article
        data-testid={`daily-card-pod-${pod.id}`}
        className="group flex flex-col bg-white border border-slate-200 rounded-sm hover:border-agg-orange/60 transition-colors p-5"
      >
        <header className="flex items-center gap-3 mb-3">
          <MarkLogo name={pod.title} src={pod.cover_art} size={40} />
          <div className="min-w-0">
            <Link
              to="/news/podcasts"
              data-testid={`daily-card-pod-name-${pod.id}`}
              className="font-display font-semibold text-[15px] text-agg-navy hover:text-agg-orange transition-colors truncate block"
            >
              {pod.title}
            </Link>
            <p className="font-sans text-[10px] uppercase tracking-[0.18em] text-agg-orange font-semibold">
              Podcast
            </p>
          </div>
          {BadgeChip && <div className="ml-auto">{BadgeChip}</div>}
        </header>

        {ep ? (
          <a
            href={ep.link || pod.apple_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`daily-card-pod-headline-${pod.id}`}
            className="flex-1 block group/h"
          >
            <h3 className="font-display font-semibold text-[16px] leading-snug text-agg-navy group-hover/h:text-agg-orange transition-colors">
              {ep.title}
            </h3>
            <p className="font-sans text-[11px] text-slate-500 mt-1.5">
              {timeAgo(ep.published_at)}
            </p>
          </a>
        ) : (
          <div className="flex-1 flex items-center text-slate-400 italic font-serif text-sm">
            No episodes yet.
          </div>
        )}

        <Link
          to="/news/podcasts"
          data-testid={`daily-card-pod-more-${pod.id}`}
          className="mt-4 inline-flex items-center justify-center self-start font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-agg-orange border border-agg-orange/40 px-3 py-1.5 rounded-sm hover:bg-agg-orange hover:text-white transition-colors"
        >
          Listen →
        </Link>
      </article>
    );
  }

  // Publisher card
  const pub = entry.publisher;
  const art = entry.article;
  const domain = domainOf(pub.homepage_url);
  const logoSrc = pub.logo_url
    || (domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64` : null);
  // Community discussion cards (Reddit threads) are kept visually distinct
  // from editorial sources: warm slate-tinted background, dashed border, and
  // a "Forum thread" label so readers know this is unmoderated community
  // chatter, not reported news.
  const isCommunity = pub.category === "community_discussion";
  const cardCls = isCommunity
    ? "group flex flex-col bg-amber-50/60 border border-dashed border-amber-300 rounded-sm hover:border-agg-orange/70 transition-colors p-5"
    : "group flex flex-col bg-white border border-slate-200 rounded-sm hover:border-agg-orange/60 transition-colors p-5";
  const categoryLabel = isCommunity
    ? "Forum thread"
    : (pub.category?.replace(/_/g, " ") || "Publisher");
  return (
    <article
      data-testid={`daily-card-pub-${pub.slug}`}
      className={cardCls}
    >
      <header className="flex items-center gap-3 mb-3">
        <MarkLogo name={pub.name} src={logoSrc} size={40} />
        <div className="min-w-0">
          <Link
            to={`/news/source/${pub.slug}`}
            data-testid={`daily-card-pub-name-${pub.slug}`}
            className="font-display font-semibold text-[15px] text-agg-navy hover:text-agg-orange transition-colors truncate block"
          >
            {pub.name}
          </Link>
          <p className="font-sans text-[10px] uppercase tracking-[0.18em] text-slate-400">
            {categoryLabel}
          </p>
        </div>
        {BadgeChip && <div className="ml-auto">{BadgeChip}</div>}
      </header>

      {art ? (
        <a
          href={art.original_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid={`daily-card-pub-headline-${pub.slug}`}
          onClick={() => trackArticleClick(art.id)}
          className="flex-1 block group/h"
        >
          <h3 className="font-display font-semibold text-[16px] leading-snug text-agg-navy group-hover/h:text-agg-orange transition-colors">
            {isHottest && (
              <span
                data-testid={`daily-card-pub-hottest-${pub.slug}`}
                title="Most-clicked article in the last 24 hours"
                aria-label="Most-clicked article in the last 24 hours"
                className="inline-block mr-1.5 align-middle"
                style={{ filter: "drop-shadow(0 1px 0 rgba(0,0,0,0.08))" }}
              >
                🔥
              </span>
            )}
            {art.title}
          </h3>
          <p className="font-sans text-[11px] text-slate-500 mt-1.5">
            {timeAgo(art.published_at)}
          </p>
        </a>
      ) : (
        <div className="flex-1 flex items-center text-slate-400 italic font-serif text-sm" data-testid={`daily-card-pub-empty-${pub.slug}`}>
          No items in the last 7 days.
        </div>
      )}

      <Link
        to={`/news/source/${pub.slug}`}
        data-testid={`daily-card-pub-more-${pub.slug}`}
        className="mt-4 inline-flex items-center justify-center self-start font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-agg-orange border border-agg-orange/40 px-3 py-1.5 rounded-sm hover:bg-agg-orange hover:text-white transition-colors"
      >
        See more articles →
      </Link>
    </article>
  );
}
