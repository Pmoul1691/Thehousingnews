import React from "react";
import NewsletterBand from "@/components/NewsletterBand";

export default function AggNewsletter() {
  return (
    <div className="max-w-2xl" data-testid="agg-newsletter-page">
      <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-2">Newsletter</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl text-agg-navy mb-6 leading-tight">
        The Housing News, every morning.
      </h1>
      <div className="font-serif text-[16px] text-slate-700 leading-relaxed space-y-5 mb-10">
        <p>
          One quiet email a day. The five headlines that matter from the residential real estate
          industry — pulled from the same 28 publishers powering the aggregator river, but
          read and shortlisted by a human before it lands in your inbox.
        </p>
        <p>
          Free. No ads. No tracking pixels. Unsubscribe in one click.
        </p>
      </div>

      <NewsletterBand />

      <div className="mt-12 pt-8 border-t border-slate-200">
        <h2 className="font-display font-semibold text-xl text-agg-navy mb-3">Looking for the paid membership?</h2>
        <p className="font-serif text-[15px] text-slate-700 leading-relaxed">
          The newsletter is free. The{" "}
          <a href="/welcome" className="text-agg-navy underline underline-offset-4 hover:text-agg-orange">members club</a>{" "}
          is a separate paid product — a calm, batched social network for working real estate producers,
          with essays, replies, and twice-daily release windows. Not required to read the aggregator.
        </p>
      </div>
    </div>
  );
}
