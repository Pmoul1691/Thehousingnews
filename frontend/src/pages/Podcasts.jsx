import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" })
      .format(new Date(iso));
  } catch { return ""; }
}
function formatDuration(s) {
  if (!s) return "";
  const m = Math.floor(s / 60), sec = s % 60;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${m}m${sec ? ` ${sec}s` : ""}`;
}

function PlayIcon() {
  return <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7L8 5z"/></svg>;
}
function AppleIcon() {
  return <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden="true"><path d="M17.0 12.4c0-2.2 1.8-3.3 1.9-3.4-1-1.5-2.6-1.7-3.2-1.7-1.4-.1-2.7.8-3.4.8-.7 0-1.8-.8-2.9-.8-1.5 0-2.9.9-3.7 2.2-1.6 2.7-.4 6.8 1.1 9 .7 1.1 1.6 2.3 2.7 2.3 1.1 0 1.5-.7 2.8-.7s1.7.7 2.9.7c1.2 0 1.9-1.1 2.7-2.2.9-1.3 1.2-2.5 1.2-2.6-.1-.1-2.3-.9-2.3-3.6zM14.7 5.3c.6-.7 1.0-1.7 0.9-2.7-.8 0-1.9.5-2.5 1.3-.6.6-1.0 1.6-.9 2.5.9.1 1.9-.5 2.5-1.1z"/></svg>;
}
function SpotifyIcon() {
  return <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.6 14.4c-.2.3-.6.4-.9.2-2.4-1.5-5.5-1.8-9.1-1-.4.1-.7-.1-.8-.5-.1-.4.1-.7.5-.8 3.9-.9 7.3-.5 10 1.1.3.2.4.6.3.9zm1.2-2.7c-.3.4-.7.5-1.1.3-2.8-1.7-7-2.2-10.3-1.2-.4.1-.9-.1-1-.5s.1-.9.5-1c3.7-1.1 8.4-.6 11.6 1.4.4.2.5.7.3 1zm.1-2.8C14.6 9 9 8.8 5.9 9.8c-.5.1-1-.2-1.2-.7s.2-1 .7-1.2c3.5-1.1 9.7-.9 13.5 1.4.5.3.6.9.4 1.4-.3.4-.9.6-1.4.3z"/></svg>;
}
function RssIcon() {
  return <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden="true"><path d="M6.18 17.82a2.18 2.18 0 1 1-4.36 0 2.18 2.18 0 0 1 4.36 0zM4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/></svg>;
}

function PodcastCard({ p, onPlay, isPlaying }) {
  const initial = (p.title || "?")[0];
  return (
    <article
      data-testid={`podcast-card-${p.id}`}
      className="group flex flex-col bg-white border border-slate-200 rounded-md p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-12px_rgba(0,0,0,0.18)] hover:border-agg-orange/50"
    >
      <header className="flex gap-4 mb-4">
        <div className="w-24 h-24 shrink-0 rounded-md overflow-hidden bg-agg-navy/5 border border-slate-100 flex items-center justify-center">
          {p.cover_art ? (
            <img
              src={p.cover_art}
              alt={`${p.title} cover art`}
              className="w-full h-full object-cover"
              loading="lazy"
              onError={(e) => { e.currentTarget.style.display = "none"; }}
            />
          ) : (
            <span className="font-display text-3xl text-agg-navy/40">{initial}</span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h2
            data-testid={`podcast-card-title-${p.id}`}
            className="font-display font-semibold text-[17px] leading-tight text-agg-navy"
          >
            {p.title}
          </h2>
          <p className="font-sans text-[12px] text-slate-500 mt-1">
            Hosted by {p.host}
          </p>
        </div>
      </header>

      <p className="font-serif text-[14px] leading-relaxed text-slate-700 mb-4">
        {p.description}
      </p>

      {p.latest_episode && (
        <div className="mb-4 pt-4 border-t border-slate-100" data-testid={`podcast-card-latest-${p.id}`}>
          <p className="font-sans text-[10px] uppercase tracking-[0.18em] text-agg-orange font-semibold mb-1.5">
            Latest episode
          </p>
          <p className="font-display text-[14px] leading-snug text-agg-navy line-clamp-2">
            {p.latest_episode.title}
          </p>
          <p className="font-sans text-[11px] text-slate-500 mt-1">
            {formatDate(p.latest_episode.published_at)}
            {p.latest_episode.duration_s ? ` · ${formatDuration(p.latest_episode.duration_s)}` : ""}
          </p>
          <button
            type="button"
            onClick={() => onPlay(p)}
            disabled={!p.latest_episode.audio_url}
            data-testid={`podcast-card-play-${p.id}`}
            className="mt-3 inline-flex items-center gap-2 bg-agg-navy text-white font-sans text-[12px] font-semibold uppercase tracking-[0.12em] px-3 py-1.5 rounded-sm hover:bg-agg-orange transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <PlayIcon />
            {isPlaying ? "Now playing" : "Play latest"}
          </button>
        </div>
      )}

      <div className="mt-auto flex flex-wrap gap-2 pt-4 border-t border-slate-100">
        <a
          href={p.apple_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid={`podcast-card-apple-${p.id}`}
          className="inline-flex items-center gap-1.5 font-sans text-[11px] font-semibold text-agg-navy border border-slate-300 px-2.5 py-1 rounded-sm hover:bg-agg-navy hover:text-white hover:border-agg-navy transition-colors"
        >
          <AppleIcon /> Apple
        </a>
        {p.spotify_url && (
          <a
            href={p.spotify_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`podcast-card-spotify-${p.id}`}
            className="inline-flex items-center gap-1.5 font-sans text-[11px] font-semibold text-[#1DB954] border border-[#1DB954]/40 px-2.5 py-1 rounded-sm hover:bg-[#1DB954] hover:text-white transition-colors"
          >
            <SpotifyIcon /> Spotify
          </a>
        )}
        {p.rss_url && (
          <a
            href={p.rss_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`podcast-card-rss-${p.id}`}
            className="inline-flex items-center gap-1.5 font-sans text-[11px] font-semibold text-agg-orange border border-agg-orange/40 px-2.5 py-1 rounded-sm hover:bg-agg-orange hover:text-white transition-colors"
          >
            <RssIcon /> RSS
          </a>
        )}
      </div>
    </article>
  );
}

function InlinePlayer({ podcast, onClose }) {
  const audioRef = useRef(null);
  const ep = podcast?.latest_episode;

  // Autoplay when a new podcast is selected. Browsers may block silently
  // until the user interacts; the manual play button on the audio element
  // is always available as a fallback.
  useEffect(() => {
    if (audioRef.current && ep?.audio_url) {
      audioRef.current.load();
      audioRef.current.play().catch(() => {});
    }
  }, [ep?.audio_url]);

  if (!podcast || !ep?.audio_url) return null;
  return (
    <section
      data-testid="podcast-now-playing"
      className="mt-12 bg-agg-navy text-white rounded-md p-6 sm:p-8 shadow-[0_18px_50px_-20px_rgba(0,0,0,0.4)]"
    >
      <div className="flex flex-col sm:flex-row gap-6 items-start">
        {podcast.cover_art && (
          <img src={podcast.cover_art} alt="" className="w-20 h-20 sm:w-28 sm:h-28 rounded-md object-cover shrink-0 border border-white/10" />
        )}
        <div className="flex-1 min-w-0">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] text-agg-orange font-semibold mb-1">
            Now playing
          </p>
          <h3 className="font-display font-semibold text-lg sm:text-xl leading-tight">
            {ep.title}
          </h3>
          <p className="font-sans text-sm text-white/70 mt-1">
            {podcast.title}
            {ep.published_at ? ` · ${formatDate(ep.published_at)}` : ""}
            {ep.duration_s ? ` · ${formatDuration(ep.duration_s)}` : ""}
          </p>
          <audio
            ref={audioRef}
            controls
            preload="none"
            data-testid="podcast-audio"
            className="mt-4 w-full"
            src={ep.audio_url}
          >
            <track kind="captions" />
          </audio>
        </div>
        <button
          type="button"
          onClick={onClose}
          data-testid="podcast-now-playing-close"
          className="font-sans text-[11px] uppercase tracking-[0.18em] text-white/60 hover:text-white"
        >
          Close
        </button>
      </div>
    </section>
  );
}

function JsonLd({ items }) {
  // PodcastSeries JSON-LD per https://schema.org/PodcastSeries
  const blob = useMemo(() => ({
    "@context": "https://schema.org",
    "@type": "ItemList",
    "name": "Top 10 Residential Real Estate Podcasts",
    "itemListOrder": "https://schema.org/ItemListOrderAscending",
    "numberOfItems": items.length,
    "itemListElement": items.map((p, i) => ({
      "@type": "ListItem",
      "position": i + 1,
      "item": {
        "@type": "PodcastSeries",
        "name": p.title,
        "description": p.description,
        "author": { "@type": "Person", "name": p.host },
        "image": p.cover_art || undefined,
        "url": p.website || p.apple_url,
        "webFeed": p.rss_url || undefined,
        "sameAs": [p.apple_url, p.spotify_url].filter(Boolean),
      },
    })),
  }), [items]);
  // Escape `<` so a publisher description containing `</script>` (or any
  // other tag) can never break out of the script element. JSON.stringify
  // alone is not enough — the resulting string is HTML, not JSON literal.
  const safe = JSON.stringify(blob).replace(/</g, "\\u003c");
  return (
    <script
      type="application/ld+json"
      data-testid="podcasts-jsonld"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: safe }}
    />
  );
}

export default function Podcasts() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(null);

  useEffect(() => {
    document.title = "Top 10 Residential Real Estate Podcasts · The Housing News";
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get("/agg/podcasts")
      .then((r) => { if (alive) setItems(r.data.items || []); })
      .catch((e) => { if (alive) setError(e?.response?.data?.detail || "Failed to load"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  return (
    <div data-testid="podcasts-page" className="pb-20">
      <JsonLd items={items} />

      <header className="mb-12 max-w-3xl">
        <p className="font-sans text-[11px] uppercase tracking-[0.22em] text-agg-orange font-semibold mb-3">
          Directory
        </p>
        <h1 className="font-display font-semibold text-3xl sm:text-4xl lg:text-5xl text-agg-navy leading-tight">
          Top 10 Residential Real Estate Podcasts
        </h1>
        <p className="font-serif text-base sm:text-lg text-slate-700 leading-relaxed mt-5">
          Ten shows we'd actually subscribe to. Each card pulls the latest episode straight from the show's RSS feed, so what you see here is what dropped this week.
        </p>
      </header>

      {loading ? (
        <p className="text-slate-500 py-12 text-center">Loading the directory.</p>
      ) : error ? (
        <p className="text-red-700 py-12 text-center" data-testid="podcasts-error">{error}</p>
      ) : (
        <section
          data-testid="podcasts-grid"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"
        >
          {items.map((p) => (
            <PodcastCard
              key={p.id}
              p={p}
              onPlay={setPlaying}
              isPlaying={playing?.id === p.id}
            />
          ))}
        </section>
      )}

      <InlinePlayer podcast={playing} onClose={() => setPlaying(null)} />

      <footer className="mt-20 pt-10 border-t border-slate-200 text-center" data-testid="podcasts-cta">
        <p className="font-serif text-base text-slate-700 max-w-xl mx-auto">
          Have a residential real estate podcast we should add?{" "}
          <a
            href="mailto:tips@thehousingnews.com?subject=Podcast%20suggestion"
            className="text-agg-orange font-semibold underline underline-offset-4 hover:opacity-80"
            data-testid="podcasts-tips-email"
          >
            Email tips@thehousingnews.com
          </a>
          .
        </p>
        <p className="mt-6">
          <Link to="/news" className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-agg-navy hover:text-agg-orange">
            ← Back to the river
          </Link>
        </p>
      </footer>
    </div>
  );
}
