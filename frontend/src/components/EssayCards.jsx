import React from "react";
import { Link } from "react-router-dom";
import { API } from "@/lib/api";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

// `FeaturedEssay`
// - When `linkTo` is provided, the whole card links to that route.
// - When `cta` is provided instead, a sign-in style CTA renders at the bottom.
//   This lets the same component serve both the authenticated Feed (clickable
//   card) and the public Landing (read-only with a sign-in nudge).
export function FeaturedEssay({ essay, linkTo, cta, testIdPrefix = "featured-essay" }) {
  if (!essay) return null;
  const author = essay.author || {};
  const coverUrl = essay.image_path ? `${API}/uploads/file/${essay.image_path}` : null;
  const inner = (
    <div className="grid sm:grid-cols-5 gap-0">
      {coverUrl && (
        <div className="sm:col-span-2 h-56 sm:h-auto overflow-hidden border-b sm:border-b-0 sm:border-r hairline">
          <img src={coverUrl} alt="" className="w-full h-full object-cover" />
        </div>
      )}
      <div className={`p-7 sm:p-9 ${coverUrl ? "sm:col-span-3" : "sm:col-span-5"}`}>
        <div className="flex items-center gap-2 mb-3">
          {essay.is_pete_pick && (
            <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete pick</span>
          )}
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">. Featured essay</span>
        </div>
        <h2 className="font-display font-semibold text-2xl sm:text-3xl ink leading-tight mb-3 group-hover:text-gold transition-colors">
          {essay.title}
        </h2>
        {essay.subtitle && (
          <p className="font-serif italic text-base text-[#2C2410]/75 leading-relaxed mb-4 line-clamp-2">{essay.subtitle}</p>
        )}
        {essay.preview && (
          <p className="prose-serif text-sm text-[#2C2410]/85 leading-relaxed line-clamp-3 mb-4">{essay.preview}</p>
        )}
        <div className="font-sans text-xs text-muted-ink">
          {author.name}{author.market ? ` . ${author.market}` : ""} . {formatDate(essay.release_at || essay.created_at)}
        </div>
        {cta}
      </div>
    </div>
  );

  if (linkTo) {
    return (
      <Link
        to={linkTo}
        data-testid={`${testIdPrefix}-${essay.post_id}`}
        className="block group border hairline rounded-sm overflow-hidden bg-cream hover:border-gold transition-colors"
      >
        {inner}
      </Link>
    );
  }
  return (
    <article
      data-testid={`${testIdPrefix}-${essay.post_id}`}
      className="block group border hairline rounded-sm overflow-hidden bg-cream"
    >
      {inner}
    </article>
  );
}

export function EssayMini({ essay, linkTo, testIdPrefix = "mini-essay" }) {
  const author = essay.author || {};
  const body = (
    <>
      {essay.is_pete_pick && (
        <p className="font-sans text-[10px] uppercase tracking-wider text-gold font-semibold mb-2">Pete pick</p>
      )}
      <p className="font-sans text-[10px] uppercase tracking-wider text-muted-ink font-semibold mb-2">Essay</p>
      <h3 className="font-display font-semibold text-base ink leading-snug group-hover:text-gold transition-colors line-clamp-3 mb-3">
        {essay.title}
      </h3>
      <p className="font-sans text-xs text-muted-ink">{author.name}{author.market ? ` . ${author.market}` : ""}</p>
    </>
  );
  if (linkTo) {
    return (
      <Link
        to={linkTo}
        data-testid={`${testIdPrefix}-${essay.post_id}`}
        className="block group border hairline rounded-sm p-5 bg-cream hover:border-gold transition-colors"
      >
        {body}
      </Link>
    );
  }
  return (
    <article data-testid={`${testIdPrefix}-${essay.post_id}`} className="block group border hairline rounded-sm p-5 bg-cream">
      {body}
    </article>
  );
}
