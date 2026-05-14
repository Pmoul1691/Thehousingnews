import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import { FeaturedEssay, EssayMini } from "@/components/EssayCards";

const signIn = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + "/auth/callback";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

function formatWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

function ShortPostRow({ post }) {
  const author = post.author || {};
  return (
    <article data-testid={`landing-post-${post.post_id}`} className="py-7">
      <div className="font-sans text-xs text-muted-ink mb-3">
        <span className="ink font-medium">{author.name || "Member"}</span>
        {author.market ? ` · ${author.market}` : ""}
        {" · "}{formatWhen(post.release_at || post.created_at)}
      </div>
      {post.text && (
        <p className="prose-serif text-[17px] leading-[1.72] ink whitespace-pre-wrap line-clamp-4 max-w-prose">
          {post.text}
        </p>
      )}
    </article>
  );
}

export default function Landing() {
  const [essays, setEssays] = useState([]);
  const [shorts, setShorts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [pubRes, essaysRes] = await Promise.all([
          api.get("/posts/public?limit=30"),
          api.get("/essays?limit=8"),
        ]);
        if (!alive) return;
        const items = pubRes.data.items || [];
        setShorts(items.filter((p) => (p.kind || "post") !== "essay").slice(0, 5));
        setEssays(essaysRes.data.items || []);
      } catch (_e) {
        // public endpoints; ignore
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const featured = essays[0];
  const restEssays = essays.slice(1, 6);

  return (
    <div data-testid="landing-page" className="bg-cream">
      {/* Masthead */}
      <section className="container-prose pt-20 sm:pt-28 pb-16 animate-fade-up">
        <p className="font-sans text-[11px] uppercase tracking-[0.28em] font-semibold text-gold mb-8" data-testid="landing-eyebrow">
          The Housing News
        </p>
        <h1 data-testid="landing-headline" className="font-display font-semibold tracking-tight text-5xl sm:text-6xl lg:text-7xl ink leading-[0.98] mb-8">
          A daily magazine
          <br />
          for the real estate
          <br />
          industry.
        </h1>
        <p className="font-serif italic text-lg sm:text-xl text-[#2C2410]/70 leading-relaxed max-w-prose mb-10">
          Written by people who close deals. Released twice a day, at 8:30am and 5:30pm.
        </p>
        <div className="flex items-center gap-6">
          <button
            onClick={signIn}
            data-testid="landing-signin-btn"
            className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-2.5 rounded-full hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
          <Link
            to="/about"
            data-testid="landing-about-link"
            className="font-sans text-sm font-medium ink hover:text-gold transition-colors"
          >
            About
          </Link>
        </div>
      </section>

      <div className="container-prose">
        <div className="border-t hairline" />
      </div>

      {/* Featured essay */}
      {loading && !featured ? (
        <section className="container-prose py-24 text-center">
          <p className="font-serif italic text-base text-muted-ink">Loading the magazine.</p>
        </section>
      ) : featured ? (
        <section className="container-prose py-20" data-testid="landing-magazine-top">
          <FeaturedEssay
            essay={featured}
            variant="quiet"
            linkTo={`/essays/${featured.post_id}`}
            testIdPrefix="landing-featured"
          />
        </section>
      ) : null}

      {/* More essays - stacked, hairline-separated rows */}
      {restEssays.length > 0 && (
        <>
          <div className="container-prose">
            <div className="border-t hairline" />
          </div>
          <section className="container-prose py-14" data-testid="landing-magazine-list">
            <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">
              More essays
            </p>
            <div className="divide-y divide-[#E8D4A0]/60">
              {restEssays.map((e) => (
                <EssayMini
                  key={e.post_id}
                  essay={e}
                  variant="row"
                  linkTo={`/essays/${e.post_id}`}
                  testIdPrefix="landing-mini"
                />
              ))}
            </div>
          </section>
        </>
      )}

      {/* From the feed - quiet stack of short notes */}
      {shorts.length > 0 && (
        <>
          <div className="container-prose">
            <div className="border-t hairline" />
          </div>
          <section className="container-prose py-14" data-testid="landing-shorts">
            <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">
              From the feed
            </p>
            <div className="divide-y divide-[#E8D4A0]/60">
              {shorts.map((p) => <ShortPostRow key={p.post_id} post={p} />)}
            </div>
          </section>
        </>
      )}

      {/* Nothing yet */}
      {!loading && !featured && shorts.length === 0 && (
        <section className="container-prose py-24 text-center" data-testid="landing-empty">
          <p className="font-serif italic text-base text-muted-ink">No posts in the last two weeks. Check back at the next release window.</p>
        </section>
      )}

      {/* Single quiet footer CTA */}
      <div className="container-prose">
        <div className="border-t hairline" />
      </div>
      <section className="container-prose py-20 text-center">
        <h2 className="font-display font-semibold text-2xl sm:text-3xl ink leading-tight mb-4">
          A small newsroom, on purpose.
        </h2>
        <p className="font-serif italic text-base text-[#2C2410]/65 leading-relaxed max-w-prose mx-auto mb-8">
          The editors read every application.
        </p>
        <button
          onClick={signIn}
          data-testid="footer-signin-btn"
          className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-2.5 rounded-full hover:opacity-90 transition-opacity"
        >
          Sign in
        </button>
      </section>
    </div>
  );
}
