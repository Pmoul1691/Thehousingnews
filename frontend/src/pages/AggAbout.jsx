import React from "react";
import { Link } from "react-router-dom";

export default function AggAbout() {
  return (
    <div className="max-w-2xl" data-testid="agg-about-page">
      <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-2">About</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl text-agg-navy mb-6 leading-tight">
        A daily aggregator for the residential real estate industry.
      </h1>

      <div className="prose prose-slate max-w-none font-serif text-[16px] leading-relaxed space-y-5">
        <p>
          The Housing News pulls the public RSS feeds from 28 publishers across the residential
          real estate industry — national trade press, regional dailies, industry blogs, data
          shops, and mortgage news. Every fifteen minutes, we fetch what publishers chose to
          put in their feed, attribute it by name, and link the headline back to the original
          article on their domain.
        </p>
        <p>
          <strong>That is the entire model.</strong>
          We do not paywall headlines. We do not host article bodies. Every click sends the
          reader to the publisher. We are a directory, not a destination.
        </p>
        <p>
          Headlines, snippets, and thumbnails are displayed verbatim from the publisher's RSS
          feed. We never rewrite, we never download images, we never AI-summarize. If a publisher
          asks us to remove their feed, we do — same day.
        </p>

        <h2 className="font-display font-semibold text-xl text-agg-navy pt-4">How items expire</h2>
        <p>
          Items older than 90 days are hidden from public pages. Items older than 120 days are
          deleted from our database. We are not building a permanent archive.
        </p>

        <h2 className="font-display font-semibold text-xl text-agg-navy pt-4">Who runs this</h2>
        <p>
          Independently published. We have spent decades in real estate — coached thousands of
          agents, helped lead teams that closed billions in client volume. The aggregator is
          free, ad-free, and tracker-free. If you want to support the work, the{" "}
          <Link to="/newsletter" className="text-agg-navy underline underline-offset-4 hover:text-agg-orange">daily email</Link>{" "}
          is free; the <Link to="/welcome" className="text-agg-navy underline underline-offset-4 hover:text-agg-orange">members club</Link> is paid.
        </p>

        <h2 className="font-display font-semibold text-xl text-agg-navy pt-4">For publishers</h2>
        <p>
          If you publish residential real estate content and want to be included, or removed,
          email <a href="mailto:hello@thehousingnews.com" className="text-agg-navy underline underline-offset-4 hover:text-agg-orange">hello@thehousingnews.com</a>.
          We answer every note.
        </p>

        <h2 className="font-display font-semibold text-xl text-agg-navy pt-4">Tech</h2>
        <p>
          The site is built and hosted on Emergent. RSS pulls use a descriptive User-Agent
          (<code className="bg-slate-100 px-1.5 py-0.5 text-[13px] rounded-sm">thehousingnews-aggregator/1.0 (+https://thehousingnews.com/about)</code>),
          honor robots.txt, and cache nothing beyond what's needed to power the public river.
        </p>
      </div>
    </div>
  );
}
