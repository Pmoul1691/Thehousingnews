import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import api, { API } from "@/lib/api";
import Replies from "@/components/Replies";
import MediaBlock from "@/components/MediaBlock";
import ShareButtons from "@/components/ShareButtons";
import PageMeta from "@/components/PageMeta";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

// Extend default sanitize schema to allow inline video/audio/iframe inserted via rich-text editor.
const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), "video", "audio", "source", "iframe"],
  attributes: {
    ...(defaultSchema.attributes || {}),
    video: ["src", "controls", "poster", "preload", "playsInline", "playsinline", "style", "width", "height"],
    audio: ["src", "controls", "preload", "style"],
    source: ["src", "type"],
    iframe: ["src", "width", "height", "frameBorder", "frameborder", "allow", "allowFullScreen", "allowfullscreen", "title", "loading"],
    "*": [...((defaultSchema.attributes && defaultSchema.attributes["*"]) || []), "className", "style"],
  },
  protocols: { ...(defaultSchema.protocols || {}), src: ["http", "https"] },
};

function formatWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { month: "long", day: "numeric", year: "numeric", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d);
  } catch { return ""; }
}

function BookmarkButton({ postId, initialBookmarked }) {
  const [bookmarked, setBookmarked] = useState(initialBookmarked);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setBookmarked(initialBookmarked); }, [initialBookmarked]);

  const toggle = async () => {
    setBusy(true);
    try {
      if (bookmarked) {
        await api.delete(`/me/bookmarks/${postId}`);
        setBookmarked(false);
        toast.success("Removed from library");
      } else {
        await api.post(`/me/bookmarks/${postId}`);
        setBookmarked(true);
        toast.success("Saved to library");
      }
    } catch {
      toast.error("Could not update");
    } finally { setBusy(false); }
  };

  return (
    <button
      data-testid="essay-bookmark-btn"
      onClick={toggle}
      disabled={busy}
      className={`font-sans text-xs uppercase tracking-wide font-semibold px-3 py-1.5 rounded-sm border transition-colors disabled:opacity-50 ${bookmarked ? "bg-gold text-cream border-gold" : "border-gold-mid text-gold hover:bg-gold hover:text-cream"}`}
    >
      {bookmarked ? "Saved" : "Save"}
    </button>
  );
}

export default function EssayDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [essay, setEssay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [progress, setProgress] = useState(0);
  const [bookmarked, setBookmarked] = useState(false);
  const markedReadRef = useRef(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setProgress(0);
    markedReadRef.current = false;
    api.get(`/essays/${id}`)
      .then((r) => { if (!cancelled) setEssay(r.data); })
      .catch(() => { if (!cancelled) setNotFound(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  // Load bookmark state when essay is loaded and user is a member
  useEffect(() => {
    if (!essay || !user || user.status !== "approved" || essay.paywall) return;
    let cancelled = false;
    api.get(`/me/bookmarks/${essay.post_id}`)
      .then((r) => { if (!cancelled) setBookmarked(!!r.data.is_bookmarked); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [essay, user]);

  // Reading progress + mark-as-read at 80%
  useEffect(() => {
    if (!essay || essay.paywall) return;
    const onScroll = () => {
      const el = bodyRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const total = el.offsetHeight;
      const viewport = window.innerHeight;
      const scrolled = Math.min(total, Math.max(0, viewport - rect.top));
      const pct = total > 0 ? Math.min(100, Math.max(0, (scrolled / total) * 100)) : 0;
      setProgress(pct);
      if (pct >= 80 && !markedReadRef.current && user && user.status === "approved") {
        markedReadRef.current = true;
        api.post(`/me/reads/${essay.post_id}`).catch(() => {});
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, [essay, user]);

  // Load the "next essay" recommendation
  const [next, setNext] = useState(null);
  useEffect(() => {
    if (!essay || essay.paywall) { setNext(null); return; }
    let cancelled = false;
    api.get(`/essays/${essay.post_id}/next`)
      .then((r) => { if (!cancelled && r.data?.next) setNext({ ...r.data.next, reason: r.data.reason }); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [essay]);

  if (loading) return <div className="container-prose py-24 text-center font-serif text-muted-ink">Loading.</div>;
  if (notFound || !essay) {
    return (
      <div className="container-prose py-24 text-center">
        <p className="uppercase-label mb-3">Not found</p>
        <p className="font-serif text-base ink/80">No essay to show.</p>
      </div>
    );
  }

  const author = essay.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const mediaList = essay.media && essay.media.length ? essay.media : (essay.image_path ? [{ kind: "image", path: essay.image_path }] : []);
  const firstVideo = mediaList.find((m) => m.kind === "video");
  const firstImage = mediaList.find((m) => m.kind === "image");
  // Video-first essays (e.g. Substack/Mux imports) lead with the player above
  // the byline so readers see what the piece actually is. Image-only essays
  // keep the historic "byline above, cover below" rhythm.
  const leadingMedia = firstVideo ? [firstVideo] : [];
  const coverUrl = !firstVideo && firstImage ? `${API}/uploads/file/${firstImage.path}` : null;
  const extraMedia = mediaList.filter((m) => m !== firstVideo && m !== firstImage);
  const canBookmark = user && user.status === "approved" && !essay.paywall;

  return (
    <>
      <PageMeta
        title={essay.title}
        description={essay.subtitle || (essay.text || "").slice(0, 200)}
        image={coverUrl}
        kind="article"
        author={author?.name}
        publishedAt={essay.release_at || essay.created_at}
      />
      {/* Reading progress bar */}
      {!essay.paywall && (
        <div className="fixed top-0 left-0 right-0 h-0.5 z-40 bg-cream" data-testid="essay-progress-track">
          <div
            data-testid="essay-progress-bar"
            className="h-full bg-gold transition-[width] duration-150 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      <article className="container-prose py-12 sm:py-16" data-testid="essay-detail">
        {essay.is_pete_pick && (
          <div className="mb-6 flex items-center gap-2" data-testid="pete-pick-banner">
            <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Staff pick</span>
            <span className="h-px flex-1 bg-gold-mid" />
          </div>
        )}
        <div className="flex items-center justify-between gap-3 mb-4">
          <p className="uppercase-label">Essay</p>
          {canBookmark && (
            <BookmarkButton postId={essay.post_id} initialBookmarked={bookmarked} />
          )}
        </div>
        <h1 className="font-display font-semibold text-4xl sm:text-5xl ink leading-[1.08] mb-5" data-testid="essay-title">{essay.title}</h1>
        {essay.subtitle && (
          <p className="font-serif italic text-lg sm:text-xl text-[#2C2410]/75 leading-relaxed mb-8" data-testid="essay-subtitle">{essay.subtitle}</p>
        )}

        <header className="flex items-center gap-3 mb-10 pb-8 border-b hairline">
          <div className="w-12 h-12 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
            {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
              <span className="font-display text-base text-gold">{(author.name || "M")[0]}</span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <Link to={`/profile/${author.user_id}`} className="font-display font-semibold text-base ink hover:text-gold transition-colors">{author.name}</Link>
            </div>
            <div className="font-sans text-xs text-muted-ink">
              {author.market ? `${author.market} . ` : ""}{formatWhen(essay.release_at || essay.created_at)}
            </div>
          </div>
        </header>

        {leadingMedia.length > 0 && (
          <div className="mb-10" data-testid="essay-leading-media">
            <MediaBlock media={leadingMedia} />
          </div>
        )}

        {coverUrl && (
          <div className="border hairline rounded-sm overflow-hidden mb-10">
            <img src={coverUrl} alt="" className="w-full max-h-[480px] object-cover" />
          </div>
        )}
        {extraMedia.length > 0 && (
          <div className="mb-10">
            <MediaBlock media={extraMedia} compact />
          </div>
        )}

        {essay.paywall ? (
          <>
            <div className="prose-serif text-lg leading-[1.75] ink/90 whitespace-pre-wrap" data-testid="essay-preview">{essay.preview}</div>
            <Paywall />
          </>
        ) : (
          <div ref={bodyRef} className="essay-body prose-serif text-lg leading-[1.78] ink/90" data-testid="essay-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw, [rehypeSanitize, SANITIZE_SCHEMA]]}
            >
              {essay.text || ""}
            </ReactMarkdown>
            {essay.source === "substack_import" && (
              <p
                data-testid="essay-source-note"
                className="not-prose mt-12 pt-6 border-t hairline font-serif italic text-sm text-muted-ink"
              >
                Originally published on Substack
                {essay.source_published_at ? `, ${new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "America/Chicago" }).format(new Date(essay.source_published_at))}` : ""}.
              </p>
            )}
          </div>
        )}

        {!essay.paywall && (
          <div className="mt-12 pt-8 border-t hairline" data-testid="essay-share">
            <ShareButtons
              url={typeof window !== "undefined" ? window.location.href : ""}
              title={essay.title}
              hasVideo={(essay.media || []).some((m) => m.kind === "video" || m.kind === "embed")}
            />
          </div>
        )}

        {!essay.paywall && (
          <div className="mt-16 pt-10 border-t hairline">
            <Replies postId={essay.post_id} replyCount={essay.reply_count || 0} />
          </div>
        )}

        {!essay.paywall && next && (
          <div className="mt-16 pt-10 border-t hairline" data-testid="next-essay">
            <p className="uppercase-label mb-4">{next.reason === "more_from_author" ? `More from ${next.author?.name || "this writer"}` : "Also in the newsroom"}</p>
            <Link to={`/essays/${next.post_id}`} className="block border hairline rounded-sm p-6 bg-cream hover:border-gold transition-colors group">
              <div className="flex gap-5">
                <div className="flex-1 min-w-0">
                  {next.is_pete_pick && (
                    <p className="font-sans text-[10px] uppercase tracking-wider font-semibold text-gold mb-2">Staff pick</p>
                  )}
                  <h3 className="font-display font-semibold text-xl ink group-hover:text-gold transition-colors leading-tight mb-2">{next.title}</h3>
                  {next.subtitle && (
                    <p className="font-serif italic text-base text-[#2C2410]/75 line-clamp-2 mb-3">{next.subtitle}</p>
                  )}
                  {next.preview && (
                    <p className="prose-serif text-sm text-[#2C2410]/80 line-clamp-2">{next.preview}</p>
                  )}
                  <div className="font-sans text-xs text-muted-ink mt-3">{next.author?.name}{next.author?.market ? ` . ${next.author.market}` : ""}</div>
                </div>
                {next.image_path && (
                  <div className="hidden sm:block w-28 h-28 shrink-0 border hairline rounded-sm overflow-hidden">
                    <img src={`${API}/uploads/file/${next.image_path}`} alt="" className="w-full h-full object-cover" />
                  </div>
                )}
              </div>
            </Link>
          </div>
        )}
      </article>
    </>
  );
}

function Paywall() {
  return (
    <div className="mt-12 relative" data-testid="essay-paywall">
      <div className="h-24 -mt-24 mb-0 pointer-events-none" style={{ background: "linear-gradient(to bottom, transparent, #FDFAF4)" }} />
      <div className="border-2 border-gold rounded-sm p-8 sm:p-10 bg-cream text-center">
        <p className="uppercase-label mb-3">Members only</p>
        <h3 className="font-display font-semibold text-2xl ink mb-3">The rest of this essay is for members.</h3>
        <p className="font-serif text-base ink/80 leading-relaxed max-w-prose mx-auto mb-6">
          The Housing News is a small newsroom of working real estate producers. The editors read every note.
        </p>
        <div className="flex items-center justify-center gap-4 flex-wrap">
          <button
            data-testid="paywall-apply-btn"
            onClick={() => {
              const redirectUrl = window.location.origin + "/auth/callback";
              window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
            }}
            className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity"
          >
            Join now
          </button>
          <Link to="/public" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
            Read the public feed
          </Link>
        </div>
      </div>
    </div>
  );
}
