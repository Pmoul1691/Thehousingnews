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
        <p data-testid="about-eyebrow" className="uppercase-label mb-5">About the room</p>
        <h1 data-testid="about-headline" className="font-display font-semibold tracking-tight text-4xl sm:text-5xl ink leading-[1.05]">
          Two release windows a day. The rest is quiet.
        </h1>
        <div className="mt-10 prose-serif text-lg leading-relaxed text-[#2C2410] max-w-prose space-y-5">
          <p>I built this because I was tired of LinkedIn.</p>
          <p>
            Twenty eight years selling and coaching in real estate. 1,600 agents trained. $2.8 billion in client sales volume. Five
            brokerages in Chicago. I never once made a deal because a stranger left a fire emoji on my post.
          </p>
          <p>
            The Ultradian Network is a feed of working operators. You write when you have something to say. The feed updates twice
            a day, at 8:30am and 5:30pm Chicago time. That is it.
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
            <p>You are accountable to the room. The room is small on purpose.</p>
          </div>
        </div>
      </section>

      <section className="border-t hairline bg-[#F5EDD6]/40">
        <div className="container-wide py-16">
          <p className="uppercase-label mb-8 text-center">Three rules of the room</p>
          <div className="grid sm:grid-cols-3 gap-12">
            <div data-testid="rule-card-1">
              <div className="font-display text-3xl font-semibold text-gold mb-3">01</div>
              <h3 className="font-display font-semibold text-lg ink mb-2">Write like you talk.</h3>
              <p className="prose-serif text-base text-[#2C2410]/80 leading-relaxed">No buzzwords. No motivational copy. If your post sounds like a LinkedIn bot, I will ask you to rewrite it.</p>
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
          <p className="uppercase-label mb-4">Who I am</p>
          <h2 className="font-display font-semibold text-2xl sm:text-3xl ink mb-6">Pete Moulton.</h2>
          <div className="prose-serif text-base sm:text-lg leading-relaxed space-y-5 ink">
            <p>I have spent 28 years in this business. I coached over 1,600 agents. The teams I helped lead closed $2.8 billion in new client volume across five Chicago brokerages.</p>
            <p>I moderate every post. I read every application. If you are in, you are in because I read your name and said yes.</p>
            <p>If you are an existing Ultradian Partners subscriber, you are auto granted. Just sign in.</p>
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
