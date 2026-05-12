import React, { useEffect, useState } from "react";
import api, { API } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

function formatWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d).replace(",", "") + " CT";
  } catch { return ""; }
}

export default function Replies({ postId, replyCount = 0 }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState("");
  const [posting, setPosting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/posts/${postId}/replies`);
      setItems(r.data.items || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && items.length === 0) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = async () => {
    if (!text.trim()) return;
    setPosting(true);
    try {
      await api.post(`/posts/${postId}/replies`, { text: text.trim() });
      setText("");
      toast.success("Reply queued for the next release window");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not reply");
    } finally {
      setPosting(false);
    }
  };

  const canReply = user && user.status === "approved";
  const visibleCount = replyCount + (open ? items.filter((r) => !r.is_released && r.user_id === user?.user_id).length : 0);

  return (
    <div className="mt-4 pt-4 border-t hairline">
      <button
        data-testid={`replies-toggle-${postId}`}
        onClick={() => setOpen((v) => !v)}
        className="font-sans text-xs font-semibold text-gold hover:opacity-80 transition-opacity tracking-wide uppercase"
      >
        {open ? "Hide replies" : `Replies${replyCount ? ` (${replyCount})` : ""}`}
      </button>

      {open && (
        <div className="mt-4 space-y-5">
          {loading ? (
            <div className="font-serif text-sm text-muted-ink">Loading.</div>
          ) : items.length === 0 ? (
            <div className="font-serif text-sm text-muted-ink">No replies yet.</div>
          ) : (
            items.map((r) => {
              const avatarUrl = r.author?.avatar_path ? `${API}/uploads/file/${r.author.avatar_path}` : null;
              return (
                <div key={r.reply_id} data-testid={`reply-${r.reply_id}`} className="flex gap-3 items-start">
                  <div className="w-8 h-8 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
                    {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
                      <span className="font-display text-xs text-gold">{(r.author?.name || "M")[0]}</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-sans text-sm font-semibold ink">{r.author?.name || "Member"}</span>
                      <span className="font-sans text-xs text-muted-ink">{formatWhen(r.created_at)}</span>
                      {!r.is_released && (
                        <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm">queued</span>
                      )}
                    </div>
                    <div className="prose-serif text-[15px] leading-relaxed ink whitespace-pre-wrap mt-1">{r.text}</div>
                  </div>
                </div>
              );
            })
          )}

          {canReply ? (
            <div className="pt-4 border-t hairline">
              <textarea
                data-testid={`reply-text-${postId}`}
                className="w-full bg-cream border hairline rounded-sm p-3 font-serif text-[15px] ink focus:outline-none focus:ring-1 focus:ring-gold min-h-[70px] resize-none"
                placeholder="Plain words. Add to the thread."
                maxLength={300}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <div className="flex items-center justify-between mt-2">
                <span className="font-sans text-xs text-muted-ink">{text.length}/300 . will release at the next window</span>
                <button
                  data-testid={`reply-submit-${postId}`}
                  onClick={submit}
                  disabled={posting || !text.trim()}
                  className="bg-gold text-cream font-sans font-semibold text-xs px-4 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {posting ? "Queueing..." : "Reply"}
                </button>
              </div>
            </div>
          ) : (
            <div className="font-sans text-xs text-muted-ink pt-2">Only approved members can reply.</div>
          )}
        </div>
      )}
    </div>
  );
}
