import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import Composer from "@/components/Composer";
import PostItem from "@/components/PostItem";
import NextReleaseTimer from "@/components/NextReleaseTimer";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";

export default function Feed() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [myPending, setMyPending] = useState([]);
  const [fetching, setFetching] = useState(true);
  const [scope, setScope] = useState(() => localStorage.getItem("feed_scope") || "everyone");

  const load = useCallback(async (currentScope) => {
    setFetching(true);
    try {
      const [feedRes, mineRes] = await Promise.all([
        api.get(`/posts/feed?scope=${currentScope}`),
        api.get("/posts/mine"),
      ]);
      setItems(feedRes.data.items || []);
      const pending = (mineRes.data.items || []).filter((p) => p.is_released === false);
      setMyPending(pending);
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status === "needs_application") { navigate("/apply", { replace: true }); return; }
    if (user.status === "pending") { navigate("/pending", { replace: true }); return; }
    if (user.status === "declined") { navigate("/declined", { replace: true }); return; }
    if (!user.has_profile) { navigate("/onboarding", { replace: true }); return; }
    load(scope);
  }, [user, loading, navigate, load, scope]);

  const setScopeAndSave = (s) => {
    setScope(s);
    localStorage.setItem("feed_scope", s);
  };

  return (
    <div className="container-prose py-12">
      <div className="flex items-end justify-between mb-10">
        <div>
          <p className="uppercase-label mb-2">Your feed</p>
          <h1 className="font-display font-semibold text-3xl ink">Posts from the room.</h1>
        </div>
        <div className="hidden sm:block"><NextReleaseTimer /></div>
      </div>

      <Composer onPosted={() => load(scope)} />

      {myPending.length > 0 && (
        <section className="mt-10" data-testid="my-pending-section">
          <p className="uppercase-label mb-4">Your queue</p>
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            {myPending.map((p) => (
              <div key={p.post_id} data-testid={`pending-${p.post_id}`} className="px-5 py-4 flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <p className="font-serif text-[15px] ink leading-relaxed line-clamp-3">{p.text}</p>
                </div>
                <div className="text-right whitespace-nowrap">
                  <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm">Queued</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="mt-12 flex items-center gap-4 border-b hairline">
        {[{k: "everyone", l: "Everyone"}, {k: "following", l: "Following"}].map((t) => (
          <button
            key={t.k}
            data-testid={`scope-${t.k}`}
            onClick={() => setScopeAndSave(t.k)}
            className={`pb-3 font-sans text-sm font-medium transition-colors ${scope === t.k ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
          >
            {t.l}
          </button>
        ))}
      </div>

      <div className="mt-8">
        {fetching ? (
          <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
        ) : items.length === 0 ? (
          <div className="border hairline rounded-sm py-16 text-center" data-testid="feed-empty">
            <p className="uppercase-label mb-3">Quiet</p>
            <p className="font-serif text-base ink/80 max-w-prose mx-auto">
              {scope === "following" ? "No released posts from people you follow yet. Switch to Everyone to see the full room." : "No posts released yet. Write the first one. The feed updates at 8:30am and 5:30pm Chicago time."}
            </p>
          </div>
        ) : (
          <div>
            {items.map((p) => <PostItem key={p.post_id} post={p} />)}
          </div>
        )}
      </div>
    </div>
  );
}
