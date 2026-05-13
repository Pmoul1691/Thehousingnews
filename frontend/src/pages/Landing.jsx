import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import BloomMark from "@/components/BloomMark";
import NextReleaseTimer from "@/components/NextReleaseTimer";
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

function ShortPostPreview({ post }) {
  const author = post.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const firstImage = (post.media || []).find((m) => m.kind === "image");
  const coverUrl = firstImage ? `${API}/uploads/file/${firstImage.path}` : (post.image_path ? `${API}/uploads/file/${post.image_path}` : null);
  return (
    <article data-testid={`landing-post-${post.post_id}`} className="border-b hairline pb-8 last:border-b-0">
      <div className="flex items-center gap-3 mb-3">
        {avatarUrl ? (
          <img src={avatarUrl} alt="" className="w-8 h-8 rounded-full object-cover" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-[#E8D4A0]/60 flex items-center justify-center font-sans text-xs font-semibold ink">
            {(author.name || "?").slice(0, 1).toUpperCase()}
          </div>
        )}
        <div className="font-sans text-xs text-muted-ink">
          <span className="ink font-medium">{author.name || "Member"}</span>
          {author.market ? ` . ${author.market}` : ""}
          {" . "}{formatWhen(post.release_at || post.created_at)} CT
        </div>
      </div>
      {post.text && (
        <p className="prose-serif text-base sm:text-lg leading-relaxed ink whitespace-pre-wrap line-clamp-6">{post.text}</p>
      )}
      {coverUrl && (
        <div className="mt-4 border hairline rounded-sm overflow-hidden">
          <img src={coverUrl} alt="" className="w-full max-h-[240px] object-cover" />
        </div>
      )}
    </article>
  );
}

export default function Landing() {
  const [essays, setEssays] = useState([]);
  const [shorts, setShorts] = useState([]);
  const [currentPrompt, setCurrentPrompt] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [pubRes, essaysRes, promptRes] = await Promise.all([
          api.get("/posts/public?limit=30"),
          api.get("/essays?limit=4"),
          api.get("/prompts/current").catch(() => ({ data: {} })),
        ]);
        if (!alive) return;
        const items = pubRes.data.items || [];
        setShorts(items.filter((p) => (p.kind || "post") !== "essay").slice(0, 6));
        setEssays(essaysRes.data.items || []);
        setCurrentPrompt(promptRes.data && promptRes.data.prompt_id ? promptRes.data : null);
      } catch (_e) {
        // public endpoints; ignore
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const featured = essays[0];
  const restEssays = essays.slice(1, 4);

  return (
    <div data-testid="landing-page">
      {/* Masthead */}
      <section className="container-wide pt-16 pb-10 animate-fade-up">
        <div className="flex items-start justify-between flex-wrap gap-6 mb-10">
          <div className="max-w-2xl">
            <div className="mb-5"><BloomMark size={64} /></div>
            <p data-testid="landing-eyebrow" className="uppercase-label mb-4">The Ultradian Network</p>
            <h1 data-testid="landing-headline" className="font-display font-semibold tracking-tight text-4xl sm:text-5xl lg:text-6xl ink leading-[1.02]">
              A magazine for working real estate operators.
            </h1>
            <p className="font-serif italic text-base sm:text-lg text-[#2C2410]/75 leading-relaxed mt-5 max-w-prose">
              Two release windows a day, at 8:30am and 5:30pm Chicago time. The rest is quiet.
            </p>
          </div>
          <div className="flex flex-col items-end gap-4">
            <div className="hidden sm:block"><NextReleaseTimer /></div>
            <div className="flex flex-wrap items-center gap-3 justify-end">
              <button
                onClick={signIn}
                data-testid="landing-signin-btn"
                className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:opacity-90 transition-opacity"
              >
                Sign in with Google
              </button>
              <button
                onClick={signIn}
                data-testid="landing-apply-btn"
                className="inline-flex items-center justify-center border border-gold ink font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:bg-gold hover:text-cream transition-colors"
              >
                Apply for membership
              </button>
            </div>
            <Link to="/about" data-testid="landing-about-link" className="font-sans text-xs uppercase tracking-wider text-muted-ink hover:text-gold transition-colors">
              What this is .
            </Link>
          </div>
        </div>
        <div className="border-t hairline" />
      </section>

      {/* Subject of the week */}
      {currentPrompt && (
        <section className="container-wide mb-10" data-testid="landing-prompt">
          <Link to="/about" className="block border-l-4 border-gold pl-5 pr-4 py-4 bg-cream hover:bg-[#F5EDD6]/40 transition-colors group">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Subject of the week</span>
              <span className="font-sans text-xs text-muted-ink">. {currentPrompt.response_count || 0} {currentPrompt.response_count === 1 ? "response" : "responses"}</span>
            </div>
            <h3 className="font-display font-semibold text-xl ink leading-snug">{currentPrompt.title}</h3>
            {currentPrompt.body && (
              <p className="font-serif text-sm text-[#2C2410]/75 leading-relaxed mt-1 line-clamp-2">{currentPrompt.body}</p>
            )}
          </Link>
        </section>
      )}

      {/* Magazine grid */}
      <section className="container-wide pb-16">
        {loading && !featured ? (
          <div className="font-serif text-base text-muted-ink py-20 text-center">Loading the magazine.</div>
        ) : (
          <>
            {featured ? (
              <div className="grid lg:grid-cols-3 gap-8 mb-16" data-testid="landing-magazine-top">
                <div className="lg:col-span-2">
                  <FeaturedEssay
                    essay={featured}
                    linkTo={`/essays/${featured.post_id}`}
                    testIdPrefix="landing-featured"
                  />
                </div>
                <div className="space-y-5">
                  <p className="uppercase-label">Also reading</p>
                  {restEssays.length === 0 ? (
                    <p className="font-serif text-sm text-muted-ink">More essays release at the next window.</p>
                  ) : (
                    restEssays.map((e) => (
                      <EssayMini
                        key={e.post_id}
                        essay={e}
                        linkTo={`/essays/${e.post_id}`}
                        testIdPrefix="landing-mini"
                      />
                    ))
                  )}
                </div>
              </div>
            ) : null}

            {shorts.length > 0 && (
              <div className="grid lg:grid-cols-3 gap-12" data-testid="landing-shorts">
                <div className="lg:col-span-2">
                  <p className="uppercase-label mb-6">From the feed</p>
                  <div className="space-y-8">
                    {shorts.map((p) => <ShortPostPreview key={p.post_id} post={p} />)}
                  </div>
                </div>
                <aside className="lg:col-span-1">
                  <div className="border hairline rounded-sm p-7 bg-[#F5EDD6]/40 sticky top-28">
                    <p className="uppercase-label mb-3">Reading without an account</p>
                    <p className="prose-serif text-base ink leading-relaxed mb-5">
                      You are seeing the last two weeks. Replies, likes, and the full archive are members only. Sign in or apply to join.
                    </p>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        onClick={signIn}
                        data-testid="landing-aside-signin-btn"
                        className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:opacity-90 transition-opacity"
                      >
                        Sign in
                      </button>
                      <Link to="/about" data-testid="landing-aside-about-link" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
                        What this is
                      </Link>
                    </div>
                  </div>
                </aside>
              </div>
            )}

            {!featured && shorts.length === 0 && (
              <div className="border hairline rounded-sm py-16 text-center" data-testid="landing-empty">
                <p className="uppercase-label mb-3">Quiet</p>
                <p className="font-serif text-base ink/80 max-w-prose mx-auto">
                  No posts in the last two weeks. Check back at the next release window.
                </p>
              </div>
            )}
          </>
        )}
      </section>

      {/* Footer CTA */}
      <section className="border-t hairline bg-[#F5EDD6]/30">
        <div className="container-prose py-16 text-center">
          <p className="uppercase-label mb-4">For real estate operators</p>
          <h2 className="font-display font-semibold text-2xl sm:text-3xl ink mb-4">A small room, on purpose.</h2>
          <p className="font-serif text-base sm:text-lg text-[#2C2410]/80 leading-relaxed max-w-prose mx-auto mb-8">
            Pete moderates every post. He reads every application. If you are in, you are in because he read your name and said yes.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <button
              onClick={signIn}
              data-testid="footer-signin-btn"
              className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity"
            >
              Sign in with Google
            </button>
            <Link to="/about" data-testid="footer-about-link" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
              Read the rules of the room
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
