import React from "react";
import { Link } from "react-router-dom";
import { API } from "@/lib/api";
import Replies from "@/components/Replies";

function formatWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d).replace(",", "") + " CT";
  } catch { return ""; }
}

export default function PostItem({ post, showReplies = true }) {
  const author = post.author || {};
  const avatarUrl = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
  const imageUrl = post.image_path ? `${API}/uploads/file/${post.image_path}` : null;
  const isQueued = post.is_released === false;

  return (
    <article data-testid={`post-${post.post_id}`} className="border-b hairline py-10 first:pt-0">
      <header className="flex items-start gap-4 mb-5">
        <div className="w-10 h-10 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
          {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
            <span className="font-display text-sm text-gold">{(author.name || "M")[0]}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <Link to={`/profile/${author.user_id}`} data-testid={`post-author-${post.post_id}`} className="font-sans text-sm font-semibold ink hover:text-gold transition-colors">
            {author.name || "Member"}
          </Link>
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
      {showReplies && !isQueued && (
        <Replies postId={post.post_id} replyCount={post.reply_count || 0} />
      )}
    </article>
  );
}
