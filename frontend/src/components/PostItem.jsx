import React, { useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import Replies from "@/components/Replies";
import FlagButton from "@/components/FlagButton";
import MediaBlock from "@/components/MediaBlock";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

// Match #word (2-30 alphanumeric/underscore) following start-of-string or whitespace.
const TAG_RE = /(^|\s)(#[A-Za-z0-9_]{2,30})\b/g;

/**
 * Render plain text with #hashtags converted to <Link> elements that route to
 * /tag/[tag]. Whitespace is preserved (whitespace-pre-wrap on the container).
 */
function renderTextWithTags(text) {
  if (!text) return null;
  const parts = [];
  let last = 0;
  let i = 0;
  TAG_RE.lastIndex = 0;
  let m;
  while ((m = TAG_RE.exec(text)) !== null) {
    const matchStart = m.index + m[1].length; // skip leading whitespace from group 1
    const tagText = m[2]; // "#word"
    const tagSlug = tagText.slice(1).toLowerCase();
    if (matchStart > last) parts.push(<span key={`t${i++}`}>{text.slice(last, matchStart)}</span>);
    parts.push(
      <Link
        key={`h${i++}`}
        to={`/tag/${tagSlug}`}
        data-testid={`post-hashtag-${tagSlug}`}
        className="text-gold hover:opacity-80 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        {tagText}
      </Link>
    );
    last = matchStart + tagText.length;
  }
  if (last < text.length) parts.push(<span key={`t${i++}`}>{text.slice(last)}</span>);
  return parts;
}

function formatWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d).replace(",", "") + " CT";
  } catch { return ""; }
}

function EssayCard({ post, user, onChange }) {
  const author = post.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const mediaList = post.media && post.media.length ? post.media : (post.image_path ? [{ kind: "image", path: post.image_path }] : []);
  const firstImage = mediaList.find((m) => m.kind === "image");
  const hasNonImageMedia = mediaList.some((m) => m.kind !== "image");
  const coverUrl = firstImage ? `${API}/uploads/file/${firstImage.path}` : null;
  const isOwner = user && user.user_id === author.user_id;
  const [busy, setBusy] = useState(false);

  const togglePick = async () => {
    setBusy(true);
    try {
      const url = post.is_pete_pick ? `/admin/posts/${post.post_id}/unpick` : `/admin/posts/${post.post_id}/pick`;
      await api.post(url);
      toast.success(post.is_pete_pick ? "Removed from staff picks" : "Added to staff picks");
      onChange && onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update");
    } finally { setBusy(false); }
  };

  return (
    <article data-testid={`post-${post.post_id}`} className="border-b hairline py-10 first:pt-0">
      {post.is_pete_pick && (
        <div className="mb-4 flex items-center gap-2" data-testid={`pete-pick-${post.post_id}`}>
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Staff pick</span>
          <span className="h-px flex-1 bg-gold-mid" />
        </div>
      )}
      <Link to={`/essays/${post.post_id}`} className="block group">
        <div className="flex items-center gap-2 mb-3">
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Essay</span>
          <span className="font-sans text-xs text-muted-ink">. {formatWhen(post.release_at || post.created_at)}</span>
        </div>
        {coverUrl && (
          <div className="border hairline rounded-sm overflow-hidden mb-5">
            <img src={coverUrl} alt="" loading="lazy" decoding="async" className="w-full max-h-[280px] object-cover" />
          </div>
        )}
        <h2 className="font-display font-semibold text-2xl sm:text-3xl ink leading-tight group-hover:text-gold transition-colors mb-2">
          {post.title}
        </h2>
        {post.subtitle && (
          <p className="font-serif italic text-base sm:text-lg text-[#2C2410]/75 leading-relaxed mb-4">{post.subtitle}</p>
        )}
        {post.preview && (
          <p className="prose-serif text-base text-[#2C2410]/85 leading-relaxed line-clamp-3">{post.preview}</p>
        )}
      </Link>
      {hasNonImageMedia && (
        <div className="mt-4">
          <MediaBlock media={mediaList.filter((m) => m.kind !== "image")} compact />
        </div>
      )}
      {post.prompt && (
        <Link to={`/prompts/${post.prompt.prompt_id}`} data-testid={`essay-prompt-${post.post_id}`} className="mt-4 inline-flex items-center gap-1.5 font-sans text-[11px] uppercase tracking-wider font-semibold text-gold border border-gold-mid px-2 py-1 rounded-sm hover:bg-gold hover:text-cream transition-colors">
          <span className="text-[9px]">▸</span>
          Subject: {post.prompt.title}
        </Link>
      )}
      <div className="flex items-center justify-between mt-5">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
            {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
              <span className="font-display text-xs text-gold">{(author.name || "M")[0]}</span>
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <Link to={`/profile/${author.user_id}`} className="font-sans text-sm font-semibold ink hover:text-gold transition-colors truncate">
                {author.name || "Member"}
              </Link>
            </div>
            {author.market && <div className="font-sans text-xs text-muted-ink">{author.market}</div>}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {user && user.is_admin && (
            <button
              data-testid={`admin-pick-${post.post_id}`}
              onClick={togglePick}
              disabled={busy}
              className="font-sans text-xs text-gold hover:opacity-80 transition-opacity disabled:opacity-50 uppercase tracking-wide"
            >
              {post.is_pete_pick ? "Unpick" : "Staff pick"}
            </button>
          )}
          {user && <FlagButton targetKind="post" targetId={post.post_id} viewerFlagged={post.viewer_flagged} isOwner={isOwner} />}
        </div>
      </div>
    </article>
  );
}

export default function PostItem({ post, showReplies = true, compact = false, onChange }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const kind = post.kind || "post";

  // Render essay as a card
  if (kind === "essay") {
    return <EssayCard post={post} user={user} onChange={onChange} />;
  }

  // Regular short post
  const author = post.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const isQueued = post.is_released === false;
  const isOwner = user && user.user_id === author.user_id;

  const togglePick = async () => {
    setBusy(true);
    try {
      const url = post.is_pete_pick ? `/admin/posts/${post.post_id}/unpick` : `/admin/posts/${post.post_id}/pick`;
      await api.post(url);
      toast.success(post.is_pete_pick ? "Removed from staff picks" : "Added to staff picks");
      onChange && onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update");
    } finally { setBusy(false); }
  };

  return (
    <article data-testid={`post-${post.post_id}`} className="border-b hairline py-10 first:pt-0">
      {post.is_pete_pick && !compact && (
        <div className="mb-4 flex items-center gap-2" data-testid={`pete-pick-${post.post_id}`}>
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Staff pick</span>
          <span className="h-px flex-1 bg-gold-mid" />
        </div>
      )}
      <header className="flex items-start gap-4 mb-5">
        <div className="w-10 h-10 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
          {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
            <span className="font-display text-sm text-gold">{(author.name || "M")[0]}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <Link to={`/profile/${author.user_id}`} data-testid={`post-author-${post.post_id}`} className="font-sans text-sm font-semibold ink hover:text-gold transition-colors">
              {author.name || "Member"}
            </Link>
          </div>
          {author.market && <div className="font-sans text-xs text-muted-ink mt-0.5">{author.market}</div>}
        </div>
        <div className="text-right whitespace-nowrap pt-1">
          {isQueued ? (
            <div data-testid={`post-queued-${post.post_id}`}>
              <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm">Queued</span>
              <div className="font-sans text-xs text-muted-ink mt-1">Releases {formatWhen(post.release_at)}</div>
            </div>
          ) : (
            <div className="font-sans text-xs text-muted-ink">{formatWhen(post.release_at || post.created_at)}</div>
          )}
        </div>
      </header>
      <div className="prose-serif text-base sm:text-lg leading-relaxed ink whitespace-pre-wrap">{renderTextWithTags(post.text)}</div>
      <MediaBlock media={post.media} imagePath={post.image_path} />
      {post.tags && post.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5" data-testid={`post-tags-${post.post_id}`}>
          {post.tags.map((t) => (
            <Link
              key={t}
              to={`/tag/${t}`}
              data-testid={`post-tag-pill-${t}`}
              className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold border border-gold-mid px-2 py-0.5 rounded-sm hover:bg-gold hover:text-cream transition-colors"
            >
              #{t}
            </Link>
          ))}
        </div>
      )}
      {post.prompt && (
        <Link to={`/prompts/${post.prompt.prompt_id}`} data-testid={`post-prompt-${post.post_id}`} className="mt-4 inline-flex items-center gap-1.5 font-sans text-[11px] uppercase tracking-wider font-semibold text-gold border border-gold-mid px-2 py-1 rounded-sm hover:bg-gold hover:text-cream transition-colors">
          <span className="text-[9px]">▸</span>
          Subject: {post.prompt.title}
        </Link>
      )}

      {!isQueued && !compact && (
        <div className="mt-3 flex items-center justify-end gap-3">
          {user && user.is_admin && (
            <button
              data-testid={`admin-pick-${post.post_id}`}
              onClick={togglePick}
              disabled={busy}
              className="font-sans text-xs text-gold hover:opacity-80 transition-opacity disabled:opacity-50 uppercase tracking-wide"
            >
              {post.is_pete_pick ? "Unpick" : "Staff pick"}
            </button>
          )}
          {user && (
            <FlagButton
              targetKind="post"
              targetId={post.post_id}
              viewerFlagged={post.viewer_flagged}
              isOwner={isOwner}
            />
          )}
        </div>
      )}

      {showReplies && !isQueued && !compact && (
        <Replies postId={post.post_id} replyCount={post.reply_count || 0} />
      )}
    </article>
  );
}
