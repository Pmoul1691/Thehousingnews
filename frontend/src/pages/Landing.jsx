import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import PageMeta from "@/components/PageMeta";

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

// MemberAvatar — real photo when an avatar_path exists, initials fallback
// otherwise. Used on the "From the feed" rows and member essay cards.
function MemberAvatar({ name, avatarPath, size = 44, className = "" }) {
  const [errored, setErrored] = useState(false);
  const letter = (name || "?").trim().charAt(0).toUpperCase() || "M";
  const dim = { width: size, height: size };
  if (avatarPath && !errored) {
    return (
      <img
        src={`${API}/uploads/file/${avatarPath}`}
        alt={name || "Member"}
        loading="lazy"
        onError={() => setErrored(true)}
        className={`rounded-full object-cover bg-cream-soft border border-gold/30 shrink-0 ${className}`}
        style={dim}
      />
    );
  }
  return (
    <div
      className={`rounded-full bg-cream-soft border border-gold/30 flex items-center justify-center shrink-0 ${className}`}
      style={dim}
      aria-label={name || "Member"}
    >
      <span className="font-display font-semibold text-gold" style={{ fontSize: Math.round(size * 0.42) }}>{letter}</span>
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

// ── Favicon helpers ───────────────────────────────────────────────────────
// Maps the editorial "source name" (as it appears in mockups + category lists)
// to a canonical hostname. Used to pull real per-publisher favicons from
// Google's favicon service so the homepage shows actual brand marks instead
// of single-letter monograms.
const SOURCE_HOSTS = {
  "HousingWire": "housingwire.com",
  "Inman": "inman.com",
  "RISMedia": "rismedia.com",
  "TRD New York": "therealdeal.com",
  "TRD Miami": "therealdeal.com",
  "TRD LA": "therealdeal.com",
  "The Real Deal": "therealdeal.com",
  "Notorious R.O.B.": "notorious-rob.com",
  "Vendor Alley": "vendoralley.com",
  "Realtor.com Research": "realtor.com",
  "Redfin": "redfin.com",
  "Mortgage News Daily": "mortgagenewsdaily.com",
  "HousingWire Mortgage": "housingwire.com",
  "BiggerPockets": "biggerpockets.com",
  "Tom Ferry": "tomferry.com",
  "Buffini": "buffini.com",
  "Miller Samuel": "millersamuel.com",
  "CRE Daily": "credaily.com",
  "Calculated Risk": "calculatedriskblog.com",
  "Eye on Housing": "eyeonhousing.org",
  "The Close": "theclose.com",
  "Commercial Observer": "commercialobserver.com",
  "Multi-Housing News": "multihousingnews.com",
};

function faviconUrl(source) {
  const host = SOURCE_HOSTS[source];
  if (!host) return null;
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
}

function SourceFavicon({ source, size = 24, className = "" }) {
  const [errored, setErrored] = useState(false);
  const url = faviconUrl(source);
  if (!url || errored) {
    return (
      <div
        className={`rounded-sm bg-[#1B2A4E] flex items-center justify-center text-white font-display font-semibold shrink-0 ${className}`}
        style={{ width: size, height: size, fontSize: Math.max(9, size * 0.45) }}
      >
        {(source || "?")[0]}
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={source}
      width={size}
      height={size}
      onError={() => setErrored(true)}
      className={`rounded-sm bg-white border border-ink/10 shrink-0 object-contain ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

function MiniDailyCard({ source, label, headline, when, badge }) {
  return (
    <div className="bg-white border border-slate-200 rounded-sm p-3">
      <div className="flex items-center gap-2 mb-2">
        <SourceFavicon source={source} size={24} />
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

function TheDailyPreview({ className = "" }) {
  return (
    <BrowserChrome url="thehousing.news/news" className={className}>
      <div data-testid="hero-daily-preview" className="bg-[#FAF7F0] p-4">
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <p className="font-sans text-[8.5px] uppercase tracking-[0.22em] font-semibold text-[#E07A2A]">The Daily</p>
            <p className="font-display font-semibold text-[15px] text-[#1B2A4E] leading-tight mt-0.5">What everyone is reading.</p>
          </div>
          <span className="font-mono text-[9px] text-slate-500">40 sources</span>
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

function ComposerPreview({ className = "" }) {
  return (
    <BrowserChrome
      url="thehousing.news/feed"
      className={`bg-cream ${className}`}
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
            Where the housing industry
            <br />
            reads.
            <br />
            <span className="text-deepred">And writes.</span>
          </h1>
          <p className="font-serif text-[18px] sm:text-[20px] leading-[1.55] text-ink/75 mt-7 max-w-[44ch]">
            A publishing network for real estate professionals. Read what the
            industry is publishing and publish what you&apos;re seeing — alongside
            twice-daily briefings pulled from 40 housing sources.
          </p>

          {/* Two co-equal pillars in the eyebrow strip */}
          <div className="grid grid-cols-2 gap-4 mt-7 max-w-[44ch]" data-testid="landing-hero-pillars">
            <div className="border-l-2 border-gold pl-3">
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Write</p>
              <p className="font-display font-semibold text-[15px] text-ink mt-1 leading-tight">
                Publish essays and short notes to your peers.
              </p>
            </div>
            <div className="border-l-2 border-gold/60 pl-3">
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Read</p>
              <p className="font-display font-semibold text-[15px] text-ink mt-1 leading-tight">
                40 sources, twice-daily, in one place.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-6 flex-wrap mt-9">
            <Link
              to="/apply"
              data-testid="landing-apply-btn"
              className="inline-flex items-center justify-center bg-ink text-cream font-sans font-semibold text-[14px] tracking-wide px-7 py-3 rounded-sm hover:bg-gold transition-colors"
            >
              Join the network
            </Link>
            <Link
              to="/essays"
              data-testid="landing-essays-btn"
              className="inline-flex items-center font-sans font-semibold text-[14px] text-ink hover:text-gold transition-colors"
            >
              Read member essays →
            </Link>
            <Link
              to="/news/latest"
              data-testid="landing-todays-edition-btn"
              className="inline-flex items-center font-sans font-semibold text-[14px] text-ink/60 hover:text-gold transition-colors"
            >
              Today&apos;s headlines →
            </Link>
          </div>

          <p className="mt-3 font-sans text-[12px] text-ink/55" data-testid="landing-pricing-note">
            Free 30-day trial when you sign up now.
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

        {/* Right — two co-equal previews. Composer (Write) on top, Daily (Read) below. */}
        <div className="relative">
          <ComposerPreview className="!mt-0 !ml-0" />
          <TheDailyPreview className="mt-6 sm:mt-8 sm:ml-12" />
          {/* Floating mini cards as background depth */}
          <div className="hidden sm:block absolute -top-6 -left-3 bg-cream-soft border border-gold/20 rounded-sm px-3 py-2 -rotate-[3deg] shadow-sm">
            <p className="font-sans text-[9px] uppercase tracking-[0.2em] text-gold/80 font-semibold">Write here</p>
            <p className="font-display text-[13px] text-ink mt-0.5">Members publishing daily</p>
          </div>
          <div className="hidden sm:block absolute bottom-6 -right-4 bg-cream-soft border border-gold/20 rounded-sm px-3 py-2 rotate-[3deg] shadow-sm">
            <p className="font-sans text-[9px] uppercase tracking-[0.2em] text-gold/80 font-semibold">40 sources</p>
            <p className="font-display text-[13px] text-ink mt-0.5">Twice daily.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── SECTION 2: The Feed — visual roll-call of syndicated sources ──────────
function FeedLogo({ name, src, href, kind }) {
  return (
    <a
      href={href}
      target={kind === "publisher" ? "_self" : "_self"}
      title={name}
      data-testid={`feed-logo-${kind}-${(name || "").toLowerCase().replace(/\s+/g, "-")}`}
      className="group inline-flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 rounded-sm bg-white border border-gold/15 hover:border-gold/60 hover:-translate-y-0.5 transition-all duration-200 shrink-0"
    >
      <img
        src={src}
        alt={name}
        width={36}
        height={36}
        loading="lazy"
        className="w-7 h-7 sm:w-8 sm:h-8 object-contain rounded-sm"
        onError={(e) => {
          const span = document.createElement("span");
          span.className = "w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center rounded-sm bg-ink text-cream font-display text-xs font-semibold";
          span.textContent = (name || "?")[0].toUpperCase();
          span.title = name || "";
          e.currentTarget.replaceWith(span);
        }}
      />
    </a>
  );
}

// Category bucket configuration — order matters; this is the visual stack.
const FEED_CATEGORIES = [
  { key: "national_trade", label: "National News" },
  { key: "regional",       label: "Regional" },
  { key: "mortgage",       label: "Mortgage" },
  { key: "data_research",  label: "Data & Research" },
  { key: "industry_blog",  label: "Blogs" },
  { key: "podcast",        label: "Podcasts" },
];

function FeedCategoryRow({ label, items }) {
  if (!items.length) return null;
  return (
    <div
      data-testid={`landing-feed-cat-${label.toLowerCase().replace(/\s+/g, "-").replace(/&/g, "and")}`}
      className="grid grid-cols-1 sm:grid-cols-[140px_1fr] gap-3 sm:gap-6 items-start py-4 border-t border-gold/15 first:border-t-0"
    >
      <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-gold pt-2 sm:pt-3">
        {label}
        <span className="ml-1.5 font-mono text-[10px] text-ink/40 normal-case tracking-normal">
          {items.length}
        </span>
      </p>
      <div className="flex items-center gap-3 flex-wrap">
        {items.map((it, i) => (
          <FeedLogo
            key={`${it.kind}-${it.name}-${i}`}
            name={it.name}
            src={it.src}
            href={it.href}
            kind={it.kind}
          />
        ))}
      </div>
    </div>
  );
}

function TheFeedSection({ publishers, podcasts }) {
  const buckets = useMemo(() => {
    // Dedupe publishers by hostname — TRD has 6 regional editions all on
    // therealdeal.com which produce identical Google favicons. When two
    // publishers share a host, prefer the entry in the broader category
    // (national_trade > regional > industry_blog > mortgage > data_research)
    // so the parent brand wins over the city-specific desk.
    const CAT_PRIORITY = {
      national_trade: 5,
      mortgage: 4,
      data_research: 3,
      regional: 2,
      industry_blog: 1,
    };
    const byHost = new Map();
    (publishers || []).forEach((p) => {
      if (!p || !p.homepage_url) return;
      let host;
      try { host = new URL(p.homepage_url).hostname.replace(/^www\./, ""); }
      catch { return; }
      const existing = byHost.get(host);
      if (!existing) {
        byHost.set(host, p);
        return;
      }
      const prevP = CAT_PRIORITY[existing.category] || 0;
      const nextP = CAT_PRIORITY[p.category] || 0;
      if (nextP > prevP) {
        byHost.set(host, p);
      } else if (nextP === prevP && (p.name || "").length < (existing.name || "").length) {
        byHost.set(host, p);
      }
    });

    const grouped = {};
    FEED_CATEGORIES.forEach((c) => { grouped[c.key] = []; });

    Array.from(byHost.entries()).forEach(([host, p]) => {
      const src = p.logo_url || `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
      const cat = p.category && grouped[p.category] ? p.category : "industry_blog";
      grouped[cat].push({
        kind: "publisher",
        name: p.name,
        src,
        href: `/news/source/${p.slug}`,
      });
    });

    grouped.podcast = (podcasts || []).filter((p) => p.title).map((p) => ({
      kind: "podcast",
      name: p.title,
      src: p.cover_art,
      href: `/news/podcasts`,
    }));

    // Sort each bucket alphabetically by name so the layout is stable
    Object.values(grouped).forEach((arr) => arr.sort((a, b) => a.name.localeCompare(b.name)));
    return grouped;
  }, [publishers, podcasts]);

  const totalSources = useMemo(
    () => Object.values(buckets).reduce((sum, arr) => sum + arr.length, 0),
    [buckets],
  );
  if (!totalSources) return null;

  return (
    <section data-testid="landing-feed-section" className="container-editorial py-20">
      <div className="flex items-end justify-between flex-wrap gap-4 mb-10">
        <div>
          <Eyebrow>The Feed</Eyebrow>
          <h2 className="font-display font-semibold text-[32px] sm:text-[42px] leading-[1.04] text-ink mt-5 tracking-tight">
            What gets syndicated, every day.
          </h2>
          <p className="font-serif text-[17px] leading-relaxed text-ink/75 mt-5 max-w-prose">
            {totalSources} sources across national news, regional desks, mortgage,
            data, blogs, and podcasts — all in one daily edition.
          </p>
        </div>
        <Link
          to="/news"
          data-testid="landing-feed-explore"
          className="font-sans font-semibold text-[14px] text-gold hover:text-ink transition-colors"
        >
          Open The Daily →
        </Link>
      </div>

      <div className="border-y border-gold/15" data-testid="landing-feed-rows">
        {FEED_CATEGORIES.map((c) => (
          <FeedCategoryRow key={c.key} label={c.label} items={buckets[c.key] || []} />
        ))}
      </div>
    </section>
  );
}

// ── SECTION 2C: Trending tags strip ────────────────────────────────────────
function TrendingTagsStrip({ tags }) {
  if (!tags || tags.length === 0) return null;
  return (
    <section
      data-testid="landing-trending-tags"
      className="container-editorial py-8 sm:py-10"
    >
      <div className="border-y border-gold/15 py-6 sm:py-7">
        <div className="flex items-baseline gap-3 mb-4 flex-wrap">
          <p className="font-sans text-[10px] uppercase tracking-[0.28em] font-semibold text-gold">
            What members are writing about
          </p>
          <span className="font-mono text-[10px] text-ink/45">last 14 days</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap" data-testid="landing-trending-tags-list">
          {tags.map((t) => (
            <Link
              key={t.tag}
              to={`/tag/${encodeURIComponent(t.tag)}`}
              data-testid={`landing-trending-tag-${t.tag}`}
              className="group inline-flex items-baseline gap-1.5 px-3 py-1.5 rounded-full bg-cream-soft border border-gold/20 hover:border-gold/60 hover:-translate-y-0.5 transition-all duration-200"
            >
              <span className="font-display font-semibold text-[14px] text-ink group-hover:text-gold transition-colors">
                #{t.tag}
              </span>
              <span className="font-mono text-[10px] text-gold/70">{t.count}</span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── SECTION 2B: The Network — visual roll-call of member writers ───────────
function TheNetworkSection({ members }) {
  if (!members || members.length < 3) return null;

  // Group members by market region for the labeled rows. This mirrors
  // TheFeedSection's category-grouped layout so the two pillars read as equals.
  const ROW_BUCKETS = [
    { key: "agents",     label: "Agents & Brokers",  match: /agent|broker|realtor/i },
    { key: "investors",  label: "Investors",         match: /invest|fund|capital/i },
    { key: "lenders",    label: "Lenders & Mortgage",match: /lender|mortgage|loan/i },
    { key: "builders",   label: "Builders & Devs",   match: /build|developer|construction/i },
    { key: "vendors",    label: "Vendors & Tech",    match: /vendor|tech|software|saas/i },
  ];

  // Best-effort bucketing using the `market` text. Anyone we can't classify
  // falls into the "Members" catch-all so they always appear somewhere.
  const buckets = { agents: [], investors: [], lenders: [], builders: [], vendors: [], members: [] };
  members.forEach((m) => {
    const blob = `${m.market || ""} ${m.snippet || ""}`;
    const hit = ROW_BUCKETS.find((b) => b.match.test(blob));
    if (hit) buckets[hit.key].push(m);
    else buckets.members.push(m);
  });

  return (
    <section data-testid="landing-network-section" className="container-editorial py-20">
      <div className="flex items-end justify-between flex-wrap gap-4 mb-10">
        <div>
          <Eyebrow>The Network</Eyebrow>
          <h2 className="font-display font-semibold text-[32px] sm:text-[42px] leading-[1.04] text-ink mt-5 tracking-tight">
            Who&apos;s publishing here, every day.
          </h2>
          <p className="font-serif text-[17px] leading-relaxed text-ink/75 mt-5 max-w-prose">
            Real estate professionals writing for their peers — not for an
            algorithm, not for likes. Members publishing market notes, essays,
            and short observations every day.
          </p>
        </div>
        <Link
          to="/essays"
          data-testid="landing-network-explore"
          className="font-sans font-semibold text-[14px] text-gold hover:text-ink transition-colors"
        >
          Read member essays →
        </Link>
      </div>

      <div className="border-y border-gold/15" data-testid="landing-network-rows">
        {[...ROW_BUCKETS, { key: "members", label: "Members" }].map((b) => {
          const items = buckets[b.key] || [];
          if (!items.length) return null;
          return (
            <div
              key={b.key}
              data-testid={`landing-network-row-${b.key}`}
              className="grid grid-cols-1 sm:grid-cols-[140px_1fr] gap-3 sm:gap-6 items-start py-4 border-t border-gold/15 first:border-t-0"
            >
              <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-gold pt-2 sm:pt-3">
                {b.label}
                <span className="ml-1.5 font-mono text-[10px] text-ink/40 normal-case tracking-normal">
                  {items.length}
                </span>
              </p>
              <div className="flex items-center gap-3 flex-wrap">
                {items.map((m) => (
                  <Link
                    key={m.user_id}
                    to={`/profile/${m.user_id}`}
                    title={`${m.name}${m.market ? " · " + m.market : ""}`}
                    data-testid={`landing-network-member-${m.user_id}`}
                    className="group inline-flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-white border border-gold/15 hover:border-gold/60 hover:-translate-y-0.5 transition-all duration-200 shrink-0 overflow-hidden"
                  >
                    <MemberAvatar name={m.name} avatarPath={m.avatar_path} size={56} className="!border-0" />
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Symmetric CTA pair to TheFeedSection's "Open The Daily" — but for writing */}
      <div className="mt-10 flex items-center gap-4 flex-wrap">
        <Link
          to="/apply"
          data-testid="landing-network-join"
          className="inline-flex items-center justify-center bg-ink text-cream font-sans font-semibold text-[13px] px-6 py-2.5 rounded-sm hover:bg-gold transition-colors"
        >
          Start writing — Join the network
        </Link>
        <Link
          to="/members"
          className="font-sans font-semibold text-[14px] text-ink/70 hover:text-gold transition-colors"
        >
          Browse all members →
        </Link>
      </div>
    </section>
  );
}

// ── SECTION 2A: Intelligence network ──────────────────────────────────────
const CATEGORY_CARDS = [
  { key: "national",   label: "National",   sources: ["HousingWire", "Inman", "RISMedia"] },
  { key: "regional",   label: "Regional",   sources: ["TRD New York", "TRD Miami", "TRD LA"] },
  { key: "blogs",      label: "Blogs",      sources: ["Notorious R.O.B.", "Miller Samuel", "Calculated Risk"] },
  { key: "data",       label: "Data",       sources: ["Realtor.com Research", "Redfin", "Eye on Housing"] },
  { key: "mortgage",   label: "Mortgage",   sources: ["Mortgage News Daily", "HousingWire Mortgage"] },
  { key: "commentary", label: "Commentary", sources: [], sample: "Member essays, market notes" },
  { key: "podcasts",   label: "Podcasts",   sources: ["BiggerPockets", "Tom Ferry", "Buffini"] },
  { key: "research",   label: "Research",   sources: [], sample: "Brokerage research, white papers" },
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
              <p className="font-display font-semibold text-[34px] text-ink leading-none">40+</p>
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-ink/55 mt-1 font-semibold">Sources</p>
            </li>
            <li>
              <p className="font-display font-semibold text-[34px] text-ink leading-none">30</p>
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-ink/55 mt-1 font-semibold">Publishers</p>
            </li>
            <li>
              <p className="font-display font-semibold text-[34px] text-ink leading-none">17</p>
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
                {c.sources && c.sources.length > 0 ? (
                  <div className="mt-2.5 flex items-center gap-2 flex-wrap">
                    <div className="flex -space-x-1.5">
                      {c.sources.map((s) => (
                        <SourceFavicon key={s} source={s} size={22} className="ring-2 ring-cream-soft" />
                      ))}
                    </div>
                    <p className="font-serif text-[13px] italic text-ink/55">
                      {c.sources.join(", ")}
                    </p>
                  </div>
                ) : (
                  <p className="font-serif text-[13px] italic text-ink/55 mt-1">{c.sample}</p>
                )}
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
              Join now
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

// ── SECTION 6.5: Members on the feed (recently active member tiles) ───────
function MembersOnTheFeedSection({ members }) {
  if (!members || members.length < 3) return null;
  return (
    <section data-testid="landing-members-feed" className="container-editorial py-24">
      <div className="flex items-end justify-between mb-12 flex-wrap gap-4">
        <div>
          <Eyebrow>From the feed</Eyebrow>
          <h2 className="font-display font-semibold text-[34px] sm:text-[40px] leading-tight text-ink mt-5">
            Members writing this week.
          </h2>
        </div>
        <Link
          to="/members"
          data-testid="landing-members-feed-all"
          className="font-sans font-semibold text-[14px] text-gold hover:text-ink transition-colors"
        >
          See all members →
        </Link>
      </div>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {members.slice(0, 6).map((m) => {
          const href = m.last_kind === "essay" && m.last_post_id
            ? `/essays/${m.last_post_id}`
            : `/profile/${m.user_id}`;
          return (
            <li key={m.user_id}>
              <Link
                to={href}
                data-testid={`landing-member-${m.user_id}`}
                className="flex items-start gap-4 bg-white border border-gold/15 rounded-sm p-5 hover:border-gold/50 hover:-translate-y-0.5 transition-all duration-200 h-full"
              >
                <MemberAvatar name={m.name} avatarPath={m.avatar_path} size={48} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <p className="font-display font-semibold text-[15px] text-ink truncate">{m.name}</p>
                    <span className="font-mono text-[10px] text-gold/70 uppercase tracking-widest shrink-0">
                      {timeAgo(m.last_post_at)}
                    </span>
                  </div>
                  {m.market && (
                    <p className="font-sans text-[11px] text-ink/55 uppercase tracking-[0.18em] font-semibold mt-0.5">
                      {m.market}
                    </p>
                  )}
                  {m.snippet && (
                    <p className="font-serif text-[14px] text-ink/75 leading-relaxed mt-3 line-clamp-3">
                      {m.snippet}
                    </p>
                  )}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
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
                <div className="flex items-center gap-3 mt-4 pt-4 border-t border-gold/10">
                  <MemberAvatar name={e.author.name} avatarPath={e.author.avatar_path} size={32} />
                  <div className="min-w-0">
                    <p className="font-display font-semibold text-[13px] text-ink truncate">{e.author.name}</p>
                    {e.author.market && (
                      <p className="font-sans text-[11px] text-ink/55 truncate">{e.author.market}</p>
                    )}
                  </div>
                </div>
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
            Start 30-day free trial
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
  // Approved members land on /today, not the marketing page.
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (authLoading) return;
    if (user && user.status === "approved") {
      navigate("/today", { replace: true });
    }
  }, [user, authLoading, navigate]);

  const [essays, setEssays] = useState([]);
  const [dailyEntries, setDailyEntries] = useState([]);
  const [publishers, setPublishers] = useState([]);
  const [podcasts, setPodcasts] = useState([]);
  const [recentMembers, setRecentMembers] = useState([]);
  const [trendingTags, setTrendingTags] = useState([]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get("/essays?limit=12").catch(() => ({ data: { items: [] } })),
      api.get("/agg/publishers-latest", { params: { hours: 36 } }).catch(() => ({ data: { items: [] } })),
      api.get("/agg/podcasts").catch(() => ({ data: { items: [] } })),
      api.get("/agg/recent-members", { params: { limit: 24 } }).catch(() => ({ data: { items: [] } })),
      api.get("/agg/trending-tags", { params: { days: 14, limit: 8 } }).catch(() => ({ data: { items: [] } })),
    ]).then(([eRes, pRes, podRes, mRes, tRes]) => {
      if (!alive) return;
      setEssays(eRes.data.items || []);
      const pubItems = (pRes.data.items || []);
      const podItems = (podRes.data.items || []);
      setPublishers(pubItems.map((e) => e.publisher).filter(Boolean));
      setPodcasts(podItems);
      setRecentMembers(mRes.data.items || []);
      setTrendingTags(tRes.data.items || []);
      const pubs = pubItems
        .filter((e) => e.article)
        .map((e) => ({ kind: "publisher", publisher: e.publisher, article: e.article }));
      const pods = podItems
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
      <PageMeta
        title="Where the housing industry reads. And writes."
        description="A daily magazine for real estate professionals. Read what the industry is publishing and publish what you're seeing — twice-daily briefings pulled from 40 housing sources, plus member essays from agents, brokers, lenders, and investors."
      />
      <HeroSection />
      <SectionDivider />
      <TheFeedSection publishers={publishers} podcasts={podcasts} />
      <TrendingTagsStrip tags={trendingTags} />
      <SectionDivider />
      <TheNetworkSection members={recentMembers} />
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
      <MembersOnTheFeedSection members={recentMembers} />
      <MemberArticlePreviews essays={essays} />
      <HeadlinesSection entries={dailyEntries} />
      <SectionDivider />
      <WhyWeExistSection />
      <FinalCtaSection />
    </div>
  );
}
