import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";

const signIn = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + "/auth/callback";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

function formatWhen(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(iso));
  } catch { return ""; }
}
function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

// ── Reusable little atoms ─────────────────────────────────────────────────
function Eyebrow({ children, className = "" }) {
  return (
    <p className={`font-sans text-[10px] uppercase tracking-[0.28em] font-semibold text-gold ${className}`}>
      {children}
    </p>
  );
}
function SectionDivider() {
  return (
    <div className="container-editorial">
      <div className="border-t border-gold/15" />
    </div>
  );
}

// ── SECTION 1: Hero w/ right-side product preview ─────────────────────────
//
// The two previews below are intentionally styled to mimic actual screenshots
// of two real products on the platform:
//   1) TheDailyPreview — mirrors the AggHome (`/news`) navy/orange aesthetic,
//      complete with publisher cards, badges, and a feed header.
//   2) ComposerPreview — mirrors the FeedCompose + Composer UI seen at /feed,
//      with the cream/gold palette and a Facebook-style write box.
//
function BrowserChrome({ url, children, className = "" }) {
  return (
    <div className={`rounded-md overflow-hidden shadow-[0_22px_50px_-26px_rgba(31,20,10,0.35)] border border-ink/10 ${className}`}>
      <div className="flex items-center gap-1.5 px-3 py-2 bg-[#EEE6D4] border-b border-ink/10">
        <span className="w-2.5 h-2.5 rounded-full bg-[#E07A5F]/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-gold/60" />
        <span className="w-2.5 h-2.5 rounded-full bg-emerald-600/50" />
        <span className="ml-3 font-mono text-[10px] tracking-tight text-ink/55 truncate">{url}</span>
      </div>
      {children}
    </div>
  );
}

function MiniDailyCard({ source, label, headline, when, badge }) {
  return (
    <div className="bg-white border border-slate-200 rounded-sm p-3">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-6 h-6 rounded-sm bg-[#1B2A4E] flex items-center justify-center text-white font-display text-[10px] font-semibold shrink-0">
          {source[0]}
        </div>
        <p className="font-display font-semibold text-[11px] text-[#1B2A4E] truncate flex-1">{source}</p>
        {badge && (
          <span className={`font-sans text-[8px] uppercase tracking-[0.14em] font-semibold px-1 py-[1px] rounded-sm ${badge.cls}`}>
            {badge.label}
          </span>
        )}
      </div>
      <p className="font-sans text-[8px] uppercase tracking-[0.16em] text-[#E07A2A] font-semibold mb-1">{label}</p>
      <p className="font-display font-semibold text-[12px] leading-snug text-[#1B2A4E] line-clamp-3">{headline}</p>
      <p className="font-sans text-[9px] text-slate-500 mt-1.5">{when}</p>
    </div>
  );
}

function TheDailyPreview() {
  return (
    <BrowserChrome url="thehousing.news/news" data-testid="hero-daily-preview">
      <div data-testid="hero-daily-preview" className="bg-[#FAF7F0] p-4">
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <p className="font-sans text-[8.5px] uppercase tracking-[0.22em] font-semibold text-[#E07A2A]">The Daily</p>
            <p className="font-display font-semibold text-[15px] text-[#1B2A4E] leading-tight mt-0.5">What everyone is reading.</p>
          </div>
          <span className="font-mono text-[9px] text-slate-500">38 sources</span>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <MiniDailyCard
            source="HousingWire"
            label="National"
            headline="Mortgage rates hold near 6.7% as Treasury yields settle."
            when="2h ago"
            badge={{ label: "Editor's Pick", cls: "bg-[#E07A2A]/10 text-[#E07A2A] border border-[#E07A2A]/30" }}
          />
          <MiniDailyCard
            source="Inman"
            label="National"
            headline="Pending sales rise in 32 metros; West softens further."
            when="3h ago"
            badge={{ label: "Trending", cls: "bg-emerald-50 text-emerald-700 border border-emerald-200" }}
          />
          <MiniDailyCard
            source="TRD Miami"
            label="Regional"
            headline="South Florida luxury inventory climbs for sixth straight week."
            when="5h ago"
            badge={{ label: "Local", cls: "bg-amber-50 text-amber-800 border border-amber-200" }}
          />
          <MiniDailyCard
            source="BiggerPockets"
            label="Podcast"
            headline="What top brokerages quietly cut from their lead spend."
            when="6h ago"
          />
        </div>
      </div>
    </BrowserChrome>
  );
}

function ComposerPreview() {
  return (
    <BrowserChrome
      url="thehousing.news/feed"
      className="-mt-3 sm:-mt-5 sm:ml-12 bg-cream"
    >
      <div data-testid="hero-composer-preview" className="bg-cream p-5">
        <p className="font-sans text-[8.5px] uppercase tracking-[0.22em] font-semibold text-gold mb-2">Write</p>
        <div className="bg-white border border-gold/20 rounded-sm p-3">
          <div className="flex items-center gap-3 pb-3 border-b border-gold/15">
            <div className="w-8 h-8 rounded-full bg-gold/15 border border-gold/40 flex items-center justify-center font-display text-[12px] font-semibold text-gold shrink-0">
              S
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display font-semibold text-[12px] text-ink leading-tight">Sarah Chen</p>
              <p className="font-sans text-[9px] text-ink/55">Chicago · Broker</p>
            </div>
            <span className="font-mono text-[9px] text-gold/70">Draft</span>
          </div>
          <p className="font-display font-semibold text-[13px] text-ink mt-3 leading-snug">
            What I told three sellers on Lincoln Park this week.
          </p>
          <p className="font-serif text-[11px] text-ink/75 leading-relaxed mt-1.5 line-clamp-3">
            Three back-to-back listings, three different price strategies. Here is what we
            tested and what actually moved buyers off the fence.
          </p>
          <div className="mt-3 pt-3 border-t border-gold/10 flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-sm bg-cream-soft border border-gold/20 font-sans text-[9px] text-ink/70">
              <svg viewBox="0 0 24 24" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/></svg>
              Photo
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-sm bg-cream-soft border border-gold/20 font-sans text-[9px] text-ink/70">
              <svg viewBox="0 0 24 24" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h12l4 4v12H4z"/></svg>
              Essay
            </span>
            <span className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-sm bg-ink text-cream font-sans text-[9px] font-semibold tracking-wide">
              Publish →
            </span>
          </div>
        </div>
      </div>
    </BrowserChrome>
  );
}

function HeroSection() {
  return (
    <section
      data-testid="landing-hero"
      className="container-editorial pt-16 sm:pt-24 pb-20 sm:pb-28"
    >
      <div className="grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-12 lg:gap-20 items-start">
        {/* Left — copy */}
        <div className="lg:pr-4">
          <Eyebrow>The Housing News</Eyebrow>
          <h1
            data-testid="landing-headline"
            className="font-display font-semibold tracking-tight text-[44px] sm:text-[58px] lg:text-[68px] leading-[0.96] text-ink mt-6"
          >
            The real estate
            <br />
            industry&apos;s
            <br />
            twice-daily briefing.
          </h1>
          <p className="font-serif text-[18px] sm:text-[20px] leading-[1.55] text-ink/75 mt-7 max-w-[42ch]">
            A magazine for the real estate industry. Twice-daily briefings, original
            reporting, member essays, and the housing news everyone else is reading —
            all in one place.
          </p>

          <div className="flex items-center gap-6 flex-wrap mt-9">
            <Link
              to="/apply"
              data-testid="landing-apply-btn"
              className="inline-flex items-center justify-center bg-ink text-cream font-sans font-semibold text-[14px] tracking-wide px-7 py-3 rounded-sm hover:bg-gold transition-colors"
            >
              Start 45-day free trial
            </Link>
            <Link
              to="/news"
              data-testid="landing-todays-edition-btn"
              className="inline-flex items-center font-sans font-semibold text-[14px] text-ink hover:text-gold transition-colors"
            >
              Read Today&apos;s Edition →
            </Link>
          </div>

          <p className="mt-3 font-sans text-[12px] text-ink/55" data-testid="landing-pricing-note">
            45 days free for invited members. After that, $12.50/mo or $100/yr.
          </p>

          <p className="mt-8 font-sans text-[12.5px] text-ink/55 tracking-wide">
            Agents · Brokers · Investors · Lenders · Builders · Teams · Vendors
          </p>

          <div className="mt-12 pt-7 border-t border-gold/20 max-w-[44ch]">
            <p className="font-serif italic text-[15.5px] leading-relaxed text-ink/75" data-testid="landing-influence-quote">
              In real estate, education and information are what build influence.
            </p>
          </div>
        </div>

        {/* Right — premium previews */}
        <div className="relative">
          <TheDailyPreview />
          <ComposerPreview />
          {/* Floating mini cards as background depth */}
          <div className="hidden sm:block absolute -top-6 -right-2 bg-cream-soft border border-gold/20 rounded-sm px-3 py-2 rotate-[3deg] shadow-sm">
            <p className="font-sans text-[9px] uppercase tracking-[0.2em] text-gold/80 font-semibold">38 sources</p>
            <p className="font-display text-[13px] text-ink mt-0.5">Twice daily.</p>
          </div>
          <div className="hidden sm:block absolute bottom-6 -left-4 bg-cream-soft border border-gold/20 rounded-sm px-3 py-2 -rotate-[2deg] shadow-sm">
            <p className="font-sans text-[9px] uppercase tracking-[0.2em] text-gold/80 font-semibold">Member Note</p>
            <p className="font-display text-[13px] text-ink mt-0.5">Chicago luxury inventory</p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── SECTION 2: Trust + positioning ────────────────────────────────────────
function TrustSection() {
  return (
    <section data-testid="landing-trust" className="container-editorial py-20">
      <div className="max-w-3xl">
        <Eyebrow>Built for professionals</Eyebrow>
        <h2 className="font-display font-semibold text-[32px] sm:text-[40px] leading-tight text-ink mt-5">
          Built for professionals actively working in housing.
        </h2>
        <p className="font-serif text-[18px] leading-relaxed text-ink/75 mt-6 max-w-prose">
          Read daily by agents, investors, lenders, brokerage leaders, builders, operators, and professionals shaping the industry.
        </p>
      </div>
      <ul className="mt-12 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-8 sm:gap-10 items-center">
        {["HousingWire", "Inman", "The Real Deal", "Realtor.com", "BiggerPockets", "Mortgage News Daily", "Curbed"].map((n) => (
          <li key={n} className="font-display text-[15px] text-ink/55 tracking-tight whitespace-nowrap">{n}</li>
        ))}
      </ul>
    </section>
  );
}

// ── SECTION 2A: Intelligence network ──────────────────────────────────────
const CATEGORY_CARDS = [
  { key: "national",   label: "National",   sample: "HousingWire, Inman, RISMedia" },
  { key: "regional",   label: "Regional",   sample: "TRD New York, TRD Miami, TRD LA" },
  { key: "blogs",      label: "Blogs",      sample: "Notorious R.O.B., Vendor Alley" },
  { key: "data",       label: "Data",       sample: "Realtor.com Research, Redfin" },
  { key: "mortgage",   label: "Mortgage",   sample: "Mortgage News Daily, HousingWire Mortgage" },
  { key: "commentary", label: "Commentary", sample: "Member essays, market notes" },
  { key: "podcasts",   label: "Podcasts",   sample: "BiggerPockets, Tom Ferry, Buffini" },
  { key: "research",   label: "Research",   sample: "Brokerage research, white papers" },
];

function IntelligenceNetworkSection() {
  return (
    <section data-testid="landing-network" className="container-editorial py-24">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-12 lg:gap-20 items-start">
        <div className="lg:sticky lg:top-24">
          <Eyebrow>The Network</Eyebrow>
          <h2 className="font-display font-semibold text-[34px] sm:text-[42px] leading-[1.04] text-ink mt-5">
            One place for the industry&apos;s most important conversations.
          </h2>
          <p className="font-serif text-[17px] leading-relaxed text-ink/75 mt-6 max-w-prose">
            The Housing News pulls together the publishers, podcasts, and writers that
            actually matter — so you can read what the industry is reading without
            opening twenty tabs.
          </p>
          <ul className="mt-10 grid grid-cols-3 gap-6 max-w-md" data-testid="landing-network-stats">
            <li>
              <p className="font-display font-semibold text-[34px] text-ink leading-none">38+</p>
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-ink/55 mt-1 font-semibold">Sources</p>
            </li>
            <li>
              <p className="font-display font-semibold text-[34px] text-ink leading-none">28</p>
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-ink/55 mt-1 font-semibold">Publishers</p>
            </li>
            <li>
              <p className="font-display font-semibold text-[34px] text-ink leading-none">10</p>
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-ink/55 mt-1 font-semibold">Podcasts</p>
            </li>
          </ul>
          <Link
            to="/news"
            data-testid="landing-network-explore"
            className="inline-flex items-center font-sans font-semibold text-[14px] text-gold hover:text-ink transition-colors mt-10"
          >
            Explore the network →
          </Link>
        </div>

        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {CATEGORY_CARDS.map((c) => (
            <li key={c.key}>
              <Link
                to={`/news/category/${c.key}`}
                data-testid={`landing-network-cat-${c.key}`}
                className="block bg-cream-soft border border-gold/25 rounded-sm p-5 hover:border-gold transition-colors group"
              >
                <p className="font-display font-semibold text-[18px] text-ink group-hover:text-gold transition-colors">{c.label}</p>
                <p className="font-serif text-[13px] italic text-ink/55 mt-1">{c.sample}</p>
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-20 pt-14 border-t border-gold/15">
        <blockquote className="font-display font-semibold text-[28px] sm:text-[36px] leading-[1.18] text-ink max-w-3xl tracking-tight">
          “Read once in the morning. Read once at night. The rest of the day belongs to your clients.”
        </blockquote>
      </div>
    </section>
  );
}

// ── SECTION 3: What you get ───────────────────────────────────────────────
const VALUE_CARDS = [
  {
    title: "Fast Industry Updates",
    body: "Stay current on the stories shaping housing — every morning, every evening.",
  },
  {
    title: "Actionable Business Intelligence",
    body: "Ideas designed to help professionals build stronger businesses and stronger conversations.",
  },
  {
    title: "Market Trends + Leadership Moves",
    body: "Understand where the industry is moving before everyone else does.",
  },
];

function WhatYouGetSection() {
  return (
    <section data-testid="landing-value" className="container-editorial py-24">
      <Eyebrow>What you get</Eyebrow>
      <h2 className="font-display font-semibold text-[34px] sm:text-[40px] leading-tight text-ink mt-5 max-w-3xl">
        Designed for the professional who has to stay sharp.
      </h2>
      <ul className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
        {VALUE_CARDS.map((c, i) => (
          <li
            key={c.title}
            data-testid={`landing-value-card-${i + 1}`}
            className="bg-white border border-gold/15 rounded-sm p-7 hover:border-gold/50 hover:-translate-y-0.5 transition-all duration-200"
          >
            <p className="font-mono text-[12px] text-gold/70">0{i + 1}</p>
            <h3 className="font-display font-semibold text-[20px] text-ink mt-3 leading-snug">{c.title}</h3>
            <p className="font-serif text-[15px] text-ink/75 leading-relaxed mt-3">{c.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── SECTION 4: Member community ────────────────────────────────────────────
function MemberCommunitySection() {
  const topics = ["Articles", "Commentary", "Market observations", "Leadership perspectives", "Local insight", "Lessons learned", "Business strategy", "Housing analysis"];
  return (
    <section data-testid="landing-community" className="container-editorial py-24">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-14 items-center">
        <div>
          <Eyebrow>The community</Eyebrow>
          <h2 className="font-display font-semibold text-[34px] sm:text-[42px] leading-[1.04] text-ink mt-5">
            Members write.
            <br />
            Members read.
          </h2>
          <p className="font-serif text-[17px] leading-relaxed text-ink/75 mt-6 max-w-prose">
            The Housing News is not just somewhere to read about real estate. It is somewhere
            to write about it — to share what you are actually seeing in your market and
            hear from other professionals doing the same.
          </p>
          <div className="mt-8 flex items-center gap-5 flex-wrap">
            <Link
              to="/apply"
              className="inline-flex items-center justify-center bg-ink text-cream font-sans font-semibold text-[14px] px-6 py-2.5 rounded-sm hover:bg-gold transition-colors"
            >
              Apply for membership
            </Link>
            <button
              onClick={signIn}
              className="font-sans font-semibold text-[14px] text-ink hover:text-gold transition-colors"
            >
              Sign in
            </button>
          </div>
        </div>
        <ul className="grid grid-cols-2 gap-3">
          {topics.map((t) => (
            <li
              key={t}
              className="bg-cream-soft border border-gold/20 rounded-sm px-4 py-3 font-display text-[15px] text-ink"
            >
              {t}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ── SECTION 5: Platform philosophy ─────────────────────────────────────────
function PhilosophySection() {
  return (
    <section data-testid="landing-philosophy" className="bg-ink text-cream py-24">
      <div className="container-editorial">
        <Eyebrow className="text-gold">Why we exist</Eyebrow>
        <blockquote className="font-display font-semibold text-[36px] sm:text-[52px] leading-[1.08] text-cream mt-7 max-w-4xl tracking-tight">
          “We believe influence should be earned through education, information, and thoughtful ideas.”
        </blockquote>
        <p className="font-serif italic text-[18px] leading-relaxed text-cream/70 mt-10 max-w-2xl">
          In real estate, education and information are what build influence.
        </p>
      </div>
    </section>
  );
}

// ── SECTION 6: Community standards ─────────────────────────────────────────
function CommunityStandardsSection() {
  const denies = [
    "Follower counts",
    "Algorithm chasing",
    "Outrage cycles",
    "Engagement bait",
    "Endless scrolling",
    "Personal-brand pressure",
  ];
  const offers = [
    "Plain writing",
    "Real numbers",
    "Local knowledge",
    "Working ideas",
    "Honest commentary",
    "Help when you can give it",
  ];
  return (
    <section data-testid="landing-standards" className="container-editorial py-24">
      <Eyebrow>What it is, what it isn&apos;t</Eyebrow>
      <h2 className="font-display font-semibold text-[40px] sm:text-[56px] leading-[1.02] text-ink mt-5 tracking-tight">
        A magazine, not a feed.
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 lg:gap-20 mt-14">
        <div>
          <p className="font-sans text-[11px] uppercase tracking-[0.22em] text-ink/40 font-semibold mb-5">No</p>
          <ul className="space-y-3">
            {denies.map((d) => (
              <li key={d} className="font-serif text-[17px] text-ink/60 line-through decoration-1 decoration-gold/50">
                {d}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-sans text-[11px] uppercase tracking-[0.22em] text-gold font-semibold mb-5">Instead</p>
          <ul className="space-y-3">
            {offers.map((o) => (
              <li key={o} className="font-display text-[18px] text-ink">{o}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

// ── SECTION 7: Member article previews ─────────────────────────────────────
function MemberArticlePreviews({ essays }) {
  if (!essays?.length) return null;
  return (
    <section data-testid="landing-essays" className="container-editorial py-24">
      <div className="flex items-end justify-between mb-12 flex-wrap gap-4">
        <div>
          <Eyebrow>From members</Eyebrow>
          <h2 className="font-display font-semibold text-[34px] sm:text-[40px] leading-tight text-ink mt-5">
            Voices from inside the industry.
          </h2>
        </div>
        <Link
          to="/essays"
          className="font-sans font-semibold text-[14px] text-gold hover:text-ink transition-colors"
        >
          All essays →
        </Link>
      </div>
      <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-7">
        {essays.slice(0, 6).map((e) => (
          <li key={e.post_id}>
            <Link
              to={`/essays/${e.post_id}`}
              data-testid={`landing-essay-${e.post_id}`}
              className="block bg-white border border-gold/15 rounded-sm p-6 hover:border-gold/50 hover:-translate-y-0.5 transition-all duration-200 h-full"
            >
              <p className="font-mono text-[11px] text-gold/70 uppercase tracking-widest">
                {formatWhen(e.release_at || e.created_at)}
                {e.read_time_minutes ? ` · ${e.read_time_minutes} min` : ""}
              </p>
              <h3 className="font-display font-semibold text-[20px] text-ink leading-snug mt-3 line-clamp-3">
                {e.title || "Untitled"}
              </h3>
              {e.author?.name && (
                <p className="font-serif text-[14px] italic text-ink/65 mt-3">
                  By {e.author.name}{e.author.market ? ` · ${e.author.market}` : ""}
                </p>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── SECTION 8: Live industry headlines ─────────────────────────────────────
function HeadlinesSection({ entries }) {
  if (!entries?.length) return null;
  return (
    <section data-testid="landing-headlines" className="bg-cream-soft py-24">
      <div className="container-editorial">
        <div className="flex items-end justify-between mb-12 flex-wrap gap-4">
          <div>
            <Eyebrow>From The Daily</Eyebrow>
            <h2 className="font-display font-semibold text-[34px] sm:text-[40px] leading-tight text-ink mt-5">
              What the industry is reading right now.
            </h2>
          </div>
          <Link
            to="/news"
            className="font-sans font-semibold text-[14px] text-gold hover:text-ink transition-colors"
          >
            Open the network →
          </Link>
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-1 max-w-6xl">
          {entries.slice(0, 10).map((e, i) => {
            const isPub = e.kind !== "podcast";
            const source = isPub ? e.publisher.name : e.podcast.title;
            const item = isPub ? e.article : e.episode;
            const href = isPub ? item.original_url : (item.link || e.podcast.apple_url);
            return (
              <li key={`h${i}`}>
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid={`landing-headline-${i}`}
                  className="group flex items-start gap-5 py-5 border-b border-gold/15 hover:bg-cream transition-colors"
                >
                  <span className="font-display font-semibold text-[22px] text-gold/35 tabular-nums w-8 shrink-0">{(i + 1).toString().padStart(2, "0")}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold truncate">{source}</span>
                      {!isPub && <span className="font-sans text-[9px] uppercase tracking-[0.16em] font-semibold text-ink/40">Podcast</span>}
                      <span className="font-sans text-[11px] text-ink/45 ml-auto">{timeAgo(item.published_at)}</span>
                    </div>
                    <p className="font-display text-[17px] leading-snug text-ink group-hover:text-gold transition-colors line-clamp-2">
                      {item.title}
                    </p>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

// ── SECTION 9: Why we exist ────────────────────────────────────────────────
function WhyWeExistSection() {
  return (
    <section data-testid="landing-why" className="container-editorial py-24">
      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-12 lg:gap-24 items-start">
        <div>
          <Eyebrow>Why The Housing News exists</Eyebrow>
          <h2 className="font-display font-semibold text-[34px] sm:text-[44px] leading-[1.04] text-ink mt-5 max-w-3xl tracking-tight">
            We were tired of finding our industry news on LinkedIn.
          </h2>
        </div>
        <div className="font-serif text-[17px] leading-relaxed text-ink/75 max-w-prose">
          <p>Most of us were getting our housing news from:</p>
          <ul className="my-5 space-y-2">
            {["A LinkedIn feed", "Group chats", "A dozen newsletters", "Whoever yelled loudest that day", "Whatever the algorithm picked"].map((s) => (
              <li key={s} className="flex items-baseline gap-3">
                <span className="text-gold/50 font-mono text-[11px] mt-1">—</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-ink">
            The Housing News puts it in one place, <em>twice a day</em>. Then it shuts up so you can work.
          </p>
        </div>
      </div>
    </section>
  );
}

// ── FINAL CTA ──────────────────────────────────────────────────────────────
function FinalCtaSection() {
  return (
    <section data-testid="landing-final-cta" className="bg-ink text-cream py-28">
      <div className="container-editorial text-center max-w-3xl">
        <Eyebrow className="text-gold">Stay ahead</Eyebrow>
        <h2 className="font-display font-semibold text-[42px] sm:text-[60px] leading-[1.02] text-cream mt-7 tracking-tight">
          Stay ahead of the housing industry.
        </h2>
        <p className="font-serif italic text-[18px] leading-relaxed text-cream/65 mt-8">
          In real estate, education and information are what build influence.
        </p>
        <div className="mt-10 flex items-center gap-6 justify-center flex-wrap">
          <Link
            to="/apply"
            data-testid="landing-final-apply"
            className="inline-flex items-center justify-center bg-gold text-ink font-sans font-semibold text-[14px] px-8 py-3 rounded-sm hover:bg-cream transition-colors"
          >
            Start 45-day free trial
          </Link>
          <Link
            to="/news"
            className="font-sans font-semibold text-[14px] text-cream/80 hover:text-gold transition-colors"
          >
            View Sample Issue →
          </Link>
        </div>
        <p className="mt-6 font-sans text-[12px] text-cream/50" data-testid="landing-final-pricing">
          $12.50/mo or $100/yr after trial.
        </p>
      </div>
    </section>
  );
}

// ── Top-level page ─────────────────────────────────────────────────────────
export default function Landing() {
  const [essays, setEssays] = useState([]);
  const [dailyEntries, setDailyEntries] = useState([]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get("/essays?limit=12").catch(() => ({ data: { items: [] } })),
      api.get("/agg/publishers-latest", { params: { hours: 36 } }).catch(() => ({ data: { items: [] } })),
      api.get("/agg/podcasts").catch(() => ({ data: { items: [] } })),
    ]).then(([eRes, pRes, podRes]) => {
      if (!alive) return;
      setEssays(eRes.data.items || []);
      const pubs = (pRes.data.items || [])
        .filter((e) => e.article)
        .map((e) => ({ kind: "publisher", publisher: e.publisher, article: e.article }));
      const pods = (podRes.data.items || [])
        .filter((p) => p.latest_episode)
        .map((p) => ({ kind: "podcast", podcast: p, episode: p.latest_episode }));
      const merged = [...pubs, ...pods].sort((a, b) => {
        const ad = (a.article || a.episode).published_at || "";
        const bd = (b.article || b.episode).published_at || "";
        return bd.localeCompare(ad);
      });
      setDailyEntries(merged);
    });
    return () => { alive = false; };
  }, []);

  return (
    <div data-testid="landing-page" className="bg-cream">
      <HeroSection />
      <SectionDivider />
      <TrustSection />
      <SectionDivider />
      <IntelligenceNetworkSection />
      <SectionDivider />
      <WhatYouGetSection />
      <SectionDivider />
      <MemberCommunitySection />
      <PhilosophySection />
      <SectionDivider />
      <CommunityStandardsSection />
      <SectionDivider />
      <MemberArticlePreviews essays={essays} />
      <HeadlinesSection entries={dailyEntries} />
      <SectionDivider />
      <WhyWeExistSection />
      <FinalCtaSection />
    </div>
  );
}
