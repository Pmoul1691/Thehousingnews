import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import api, { API } from "@/lib/api";
import Replies from "@/components/Replies";
import { useAuth } from "@/context/AuthContext";

function formatWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { month: "long", day: "numeric", year: "numeric", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d);
  } catch { return ""; }
}

export default function EssayDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [essay, setEssay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get(`/essays/${id}`)
      .then((r) => { if (!cancelled) setEssay(r.data); })
      .catch(() => { if (!cancelled) setNotFound(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

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
  const coverUrl = essay.image_path ? `${API}/uploads/file/${essay.image_path}` : null;

  return (
    <article className="container-prose py-12 sm:py-16" data-testid="essay-detail">
      {essay.is_pete_pick && (
        <div className="mb-6 flex items-center gap-2" data-testid="pete-pick-banner">
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete pick</span>
          <span className="h-px flex-1 bg-gold-mid" />
        </div>
      )}
      <p className="uppercase-label mb-4">Essay</p>
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
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Link to={`/profile/${author.user_id}`} className="font-display font-semibold text-base ink hover:text-gold transition-colors">{author.name}</Link>
            {author.is_supporter && <span className="text-gold text-sm leading-none">✦</span>}
          </div>
          <div className="font-sans text-xs text-muted-ink">
            {author.market ? `${author.market} . ` : ""}{formatWhen(essay.release_at || essay.created_at)}
          </div>
        </div>
      </header>

      {coverUrl && (
        <div className="border hairline rounded-sm overflow-hidden mb-10">
          <img src={coverUrl} alt="" className="w-full max-h-[480px] object-cover" />
        </div>
      )}

      {essay.paywall ? (
        <>
          <div className="prose-serif text-lg leading-[1.75] ink/90 whitespace-pre-wrap" data-testid="essay-preview">{essay.preview}</div>
          <Paywall />
        </>
      ) : (
        <div className="essay-body prose-serif text-lg leading-[1.78] ink/90" data-testid="essay-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{essay.text || ""}</ReactMarkdown>
        </div>
      )}

      {!essay.paywall && (
        <div className="mt-16 pt-10 border-t hairline">
          <Replies postId={essay.post_id} replyCount={essay.reply_count || 0} />
        </div>
      )}
    </article>
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
          The Network is a small room of working real estate operators. Pete reads every application.
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
            Apply for membership
          </button>
          <Link to="/public" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
            Read the public feed
          </Link>
        </div>
      </div>
    </div>
  );
}
