import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

export default function Library() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    api.get("/me/bookmarks").then((r) => setItems(r.data.items || [])).finally(() => setFetching(false));
  }, [user, loading, navigate]);

  const remove = async (postId) => {
    try {
      await api.delete(`/me/bookmarks/${postId}`);
      setItems((arr) => arr.filter((x) => x.post_id !== postId));
      toast.success("Removed");
    } catch {
      toast.error("Could not remove");
    }
  };

  return (
    <div className="container-prose py-12" data-testid="library-page">
      <div className="mb-10">
        <p className="uppercase-label mb-2">Saved for later</p>
        <h1 className="font-display font-semibold text-4xl ink leading-tight">Your library.</h1>
        <p className="font-serif text-base text-muted-ink mt-3 max-w-2xl">
          Essays you bookmarked. Yours only. No one else sees this list.
        </p>
      </div>

      {fetching ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="library-empty">
          <p className="uppercase-label mb-3">Empty</p>
          <p className="font-serif text-base ink/80 max-w-prose mx-auto mb-6">
            You have not bookmarked anything yet. Open an essay and tap Save to keep it here.
          </p>
          <Link to="/essays" data-testid="library-browse-link" className="font-sans text-sm font-semibold text-gold underline underline-offset-4 decoration-gold-mid">
            Browse essays
          </Link>
        </div>
      ) : (
        <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="library-list">
          {items.map((b) => {
            const author = b.author || {};
            const coverUrl = b.image_path ? `${API}/uploads/file/${b.image_path}` : null;
            return (
              <div key={b.post_id} data-testid={`library-item-${b.post_id}`} className="p-5 flex gap-4 items-start">
                {coverUrl && (
                  <div className="hidden sm:block w-24 h-24 shrink-0 border hairline rounded-sm overflow-hidden">
                    <img src={coverUrl} alt="" className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <Link to={`/essays/${b.post_id}`} className="block group">
                    <h3 className="font-display font-semibold text-lg ink leading-snug group-hover:text-gold transition-colors mb-1">
                      {b.title || "Untitled"}
                    </h3>
                    {b.subtitle && (
                      <p className="font-serif italic text-sm text-[#2C2410]/75 line-clamp-2 mb-2">{b.subtitle}</p>
                    )}
                  </Link>
                  <div className="font-sans text-xs text-muted-ink">
                    {author.name}{author.market ? ` . ${author.market}` : ""} . Saved {formatDate(b.bookmarked_at)}
                  </div>
                </div>
                <button
                  data-testid={`library-remove-${b.post_id}`}
                  onClick={() => remove(b.post_id)}
                  className="font-sans text-xs text-muted-ink hover:text-deepred transition-colors uppercase tracking-wide"
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
