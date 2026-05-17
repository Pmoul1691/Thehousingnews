import React from "react";
import { Helmet } from "react-helmet-async";

/**
 * Drop this anywhere in a route component to set per-page SEO + share tags.
 * All props optional. Anything we don't set inherits from index.html defaults.
 *
 * Tags emitted: <title>, meta description, canonical, OG title/desc/image/url
 * (og:type defaults to "article" if `kind="article"`), Twitter summary card.
 */
export default function PageMeta({
  title,
  description,
  image,
  kind = "website",
  author,
  publishedAt,
}) {
  const base = "https://thehousingnews.com";
  const url = typeof window !== "undefined" ? window.location.href : base;
  const fullTitle = title ? `${title} · The Housing News` : "The Housing News";
  const og = image && image.startsWith("http") ? image : (image ? `${base}${image}` : `${base}/og-image.png`);
  return (
    <Helmet>
      <title>{fullTitle}</title>
      {description ? <meta name="description" content={description} /> : null}
      <link rel="canonical" href={url} />

      <meta property="og:site_name" content="The Housing News" />
      <meta property="og:type" content={kind === "article" ? "article" : "website"} />
      <meta property="og:title" content={title || "The Housing News"} />
      {description ? <meta property="og:description" content={description} /> : null}
      <meta property="og:image" content={og} />
      <meta property="og:url" content={url} />
      {kind === "article" && author ? <meta property="article:author" content={author} /> : null}
      {kind === "article" && publishedAt ? <meta property="article:published_time" content={publishedAt} /> : null}

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title || "The Housing News"} />
      {description ? <meta name="twitter:description" content={description} /> : null}
      <meta name="twitter:image" content={og} />
    </Helmet>
  );
}
