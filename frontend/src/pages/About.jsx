import React from "react";
import { Link } from "react-router-dom";
import BloomMark from "@/components/BloomMark";

export default function About() {
  const signIn = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/auth/callback";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div data-testid="about-page">
      <section className="container-prose pt-20 pb-16 animate-fade-up">
        <div className="mb-8"><BloomMark size={72} /></div>
        <p data-testid="about-eyebrow" className="uppercase-label mb-5">The masthead</p>
        <h1 data-testid="about-headline" className="font-display font-semibold tracking-tight text-4xl sm:text-5xl ink leading-[1.05]">
          Two release windows a day. The rest is quiet.
        </h1>
        <div className="mt-10 prose-serif text-lg leading-relaxed text-[#2C2410] max-w-prose space-y-5">
          <p>The Housing News was built because we got tired of LinkedIn.</p>
          <p>
            We are real estate producers. Decades of experience between us. Thousands of agents trained. Billions in client sales volume.
            No deal was ever made because a stranger left a fire emoji on a post.
          </p>
          <p>
            The Housing News is a daily magazine for the real estate industry. You write when you have something to say. The
            magazine releases twice a day, at 8:30am and 5:30pm Chicago time. That is it.
          </p>
          <p>No follower counts. No trending tab. No outrage. No selling courses to each other.</p>
        </div>
      </section>

      <section className="border-t hairline">
        <div className="container-prose py-16">
          <p className="uppercase-label mb-4">What this is</p>
          <h2 className="font-display font-semibold text-2xl sm:text-3xl ink mb-6">A calm-by-design place to think out loud.</h2>
          <div className="prose-serif text-base sm:text-lg leading-relaxed space-y-5 ink">
            <p>
              Every member writes one post when they want. Maybe none on Tuesday. Maybe three on Friday. Posts queue and release at
              8:30am and 5:30pm America/Chicago time. You read in two sittings, not seventy.
            </p>
            <p>
              Every member states three public objectives. The things you are actually working on this quarter. You can revise them.
              The platform remembers the prior version. That is the entire game.
            </p>
            <p>You are accountable to the newsroom. The newsroom is small on purpose.</p>
          </div>
        </div>
      </section>

      <section className="border-t hairline bg-[#F5EDD6]/40">
        <div className="container-wide py-16">
          <p className="uppercase-label mb-8 text-center">Three rules of the newsroom</p>
          <div className="grid sm:grid-cols-3 gap-12">
            <div data-testid="rule-card-1">
              <div className="font-display text-3xl font-semibold text-gold mb-3">01</div>
              <h3 className="font-display font-semibold text-lg ink mb-2">Write like you talk.</h3>
              <p className="prose-serif text-base text-[#2C2410]/80 leading-relaxed">No buzzwords. No motivational copy. If a post sounds like a LinkedIn bot, the editors will ask for a rewrite.</p>
            </div>
            <div data-testid="rule-card-2">
              <div className="font-display text-3xl font-semibold text-gold mb-3">02</div>
              <h3 className="font-display font-semibold text-lg ink mb-2">Be specific.</h3>
              <p className="prose-serif text-base text-[#2C2410]/80 leading-relaxed">Numbers. Names of streets. What the seller actually said on the phone. The texture is the value.</p>
            </div>
            <div data-testid="rule-card-3">
              <div className="font-display text-3xl font-semibold text-gold mb-3">03</div>
              <h3 className="font-display font-semibold text-lg ink mb-2">Help when you can.</h3>
              <p className="prose-serif text-base text-[#2C2410]/80 leading-relaxed">Someone in another market asks a question. You know the answer. You write a paragraph. That is the whole product.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t hairline">
        <div className="container-prose py-16">
          <p className="uppercase-label mb-4">The editors</p>
          <h2 className="font-display font-semibold text-2xl sm:text-3xl ink mb-6">A working newsroom.</h2>
          <div className="prose-serif text-base sm:text-lg leading-relaxed space-y-5 ink">
            <p>We have spent decades in real estate. We have coached thousands of agents. The teams we helped lead have closed billions in new client volume.</p>
            <p>We want to hear from you personally. We read every new member application. We welcome all opinions, perspectives, and factual presentations.</p>
            <p>If you are an existing Ultradian Partners client or Ultradia.io subscriber, you are automatically granted. Just sign in.</p>
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <button
              onClick={signIn}
              data-testid="about-signin-btn"
              className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity"
            >
              Sign in with Google
            </button>
            <Link to="/" data-testid="about-back-link" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
              Back to the magazine
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
