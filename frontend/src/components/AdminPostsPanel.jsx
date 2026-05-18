import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";

const STATUSES = [
  { v: "", l: "All" },
  { v: "approved", l: "Approved" },
  { v: "pending_release", l: "Pending release" },
  { v: "hidden", l: "Hidden" },
  { v: "declined", l: "Declined" },
];

export default function AdminPostsPanel() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("approved");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [actingId, setActingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (status) params.status = status;
      if (q.trim()) params.q = q.trim();
      const r = await api.get("/admin/posts/recent", { params });
      setItems(r.data?.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load posts");
    } finally { setLoading(false); }
  }, [status, q]);

  useEffect(() => { load(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [status]);

  const hide = async (postId) => {
    if (!window.confirm("Take this post down? It will be hidden from feeds and search.")) return;
    setActingId(postId + "hide");
    try {
      await api.post(`/admin/posts/${postId}/hide`);
      toast.success("Post hidden");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not hide");
    } finally { setActingId(null); }
  };

  const unhide = async (postId) => {
    setActingId(postId + "unhide");
    try {
      await api.post(`/admin/posts/${postId}/unhide`);
      toast.success("Post restored");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not unhide");
    } finally { setActingId(null); }
  };

  return (
    <div data-testid="admin-posts-panel">
      <p className="prose-serif text-sm text-muted-ink mb-6 max-w-prose">
        Browse all posts and take down anything that shouldn't be live. Hidden posts can be restored.
      </p>
      <div className="flex items-end gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3 border-b hairline overflow-x-auto">
          {STATUSES.map((s) => (
            <button
              key={s.v || "all"}
              data-testid={`posts-status-${s.v || "all"}`}
              onClick={() => setStatus(s.v)}
              className={`pb-3 font-sans text-sm font-medium transition-colors whitespace-nowrap ${
                status === s.v ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"
              }`}
            >
              {s.l}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <form
          onSubmit={(e) => { e.preventDefault(); load(); }}
          className="flex items-center gap-2"
        >
          <input
            data-testid="posts-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search title / text…"
            className="bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold w-56"
          />
          <button
            type="submit"
            className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity px-3 py-2"
          >
            Search
          </button>
        </form>
      </div>

      {loading ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="posts-empty">
          <p className="font-serif text-base ink/80">No posts match.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((p) => {
            const isHidden = p.status === "hidden";
            return (
              <article
                key={p.post_id}
                data-testid={`admin-post-${p.post_id}`}
                className={`border hairline rounded-sm p-5 ${isHidden ? "bg-deepred/5 border-deepred/30" : "bg-cream"}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                  <div className="min-w-0 flex-1">
                    {p.title && (
                      <h3 className="font-display font-semibold text-base ink truncate">{p.title}</h3>
                    )}
                    <p className="prose-serif text-sm ink/85 leading-relaxed line-clamp-3 mt-1">
                      {p.snippet || <span className="italic text-muted-ink">No body text</span>}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="flex items-center gap-2 flex-wrap justify-end mb-1">
                      <span className="font-sans text-[10px] uppercase tracking-wide text-gold font-semibold">
                        {p.kind}
                      </span>
                      <span className={`font-sans text-[10px] uppercase tracking-wide font-semibold ${
                        isHidden ? "text-deepred" : "text-muted-ink"
                      }`}>
                        {p.status}
                      </span>
                    </div>
                    <div className="font-sans text-[11px] text-muted-ink">
                      {p.author?.name || "—"}
                    </div>
                    <div className="font-sans text-[10px] text-muted-ink mt-0.5">
                      {p.created_at ? new Date(p.created_at).toLocaleString() : ""}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 pt-3 border-t hairline">
                  <Link
                    to={`/essays/${p.post_id}`}
                    className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity"
                  >
                    View →
                  </Link>
                  <div className="flex-1" />
                  {isHidden ? (
                    <button
                      data-testid={`admin-unhide-${p.post_id}`}
                      onClick={() => unhide(p.post_id)}
                      disabled={actingId === p.post_id + "unhide"}
                      className="font-sans text-xs uppercase tracking-wider font-semibold border hairline px-3 py-1.5 rounded-sm hover:bg-gold hover:text-cream hover:border-gold transition-colors disabled:opacity-40"
                    >
                      Restore
                    </button>
                  ) : (
                    <button
                      data-testid={`admin-takedown-${p.post_id}`}
                      onClick={() => hide(p.post_id)}
                      disabled={actingId === p.post_id + "hide"}
                      className="font-sans text-xs uppercase tracking-wider font-semibold border border-deepred text-deepred px-3 py-1.5 rounded-sm hover:bg-deepred hover:text-cream transition-colors disabled:opacity-40"
                    >
                      Take down
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
