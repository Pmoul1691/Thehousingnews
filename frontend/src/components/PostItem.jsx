import React, { useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import Replies from "@/components/Replies";
import FlagButton from "@/components/FlagButton";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

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
  const coverUrl = post.image_path ? `${API}/uploads/file/${post.image_path}` : null;
  const isOwner = user && user.user_id === author.user_id;
  const [busy, setBusy] = useState(false);

  const togglePick = async () => {
    setBusy(true);
    try {
      const url = post.is_pete_pick ? `/admin/posts/${post.post_id}/unpick` : `/admin/posts/${post.post_id}/pick`;
      await api.post(url);
      toast.success(post.is_pete_pick ? "Removed from Pete picks" : "Added to Pete picks");
      onChange && onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update");
    } finally { setBusy(false); }
  };

  return (
    <article data-testid={`post-${post.post_id}`} className="border-b hairline py-10 first:pt-0">
      {post.is_pete_pick && (
        <div className="mb-4 flex items-center gap-2" data-testid={`pete-pick-${post.post_id}`}>
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete pick</span>
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
            <img src={coverUrl} alt="" className="w-full max-h-[280px] object-cover" />
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
              {author.is_supporter && <span className="text-gold text-sm leading-none">✦</span>}
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
              {post.is_pete_pick ? "Unpick" : "Pete pick"}
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
  const kind = post.kind || "post";

  // Render essay as a card
  if (kind === "essay") {
    return <EssayCard post={post} user={user} onChange={onChange} />;
  }

  // Regular short post
  const author = post.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const imageUrl = post.image_path ? `${API}/uploads/file/${post.image_path}` : null;
  const isQueued = post.is_released === false;
  const isOwner = user && user.user_id === author.user_id;
  const [busy, setBusy] = useState(false);

  const togglePick = async () => {
    setBusy(true);
    try {
      const url = post.is_pete_pick ? `/admin/posts/${post.post_id}/unpick` : `/admin/posts/${post.post_id}/pick`;
      await api.post(url);
      toast.success(post.is_pete_pick ? "Removed from Pete picks" : "Added to Pete picks");
      onChange && onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update");
    } finally { setBusy(false); }
  };

  return (
    <article data-testid={`post-${post.post_id}`} className="border-b hairline py-10 first:pt-0">
      {post.is_pete_pick && !compact && (
        <div className="mb-4 flex items-center gap-2" data-testid={`pete-pick-${post.post_id}`}>
          <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete pick</span>
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
            {author.is_supporter && (
              <span data-testid={`supporter-badge-${post.post_id}`} title="Network supporter" className="text-gold text-sm leading-none">✦</span>
            )}
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
      <div className="prose-serif text-base sm:text-lg leading-relaxed ink whitespace-pre-wrap">{post.text}</div>
      {imageUrl && (
        <div className="mt-5 border hairline rounded-sm overflow-hidden">
          <img src={imageUrl} alt="" className="w-full max-h-[520px] object-cover" />
        </div>
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
              {post.is_pete_pick ? "Unpick" : "Pete pick"}
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
