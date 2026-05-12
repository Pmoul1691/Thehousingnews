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
  const [fetching, setFetching] = useState(true);

  const load = useCallback(async () => {
    setFetching(true);
    try {
      const r = await api.get("/posts/feed");
      setItems(r.data.items || []);
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
    load();
  }, [user, loading, navigate, load]);

  return (
    <div className="container-prose py-12">
      <div className="flex items-end justify-between mb-10">
        <div>
          <p className="uppercase-label mb-2">Your feed</p>
          <h1 className="font-display font-semibold text-3xl ink">Posts from the room.</h1>
        </div>
        <div className="hidden sm:block"><NextReleaseTimer /></div>
      </div>

      <Composer onPosted={load} />

      <div className="mt-12">
        {fetching ? (
          <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
        ) : items.length === 0 ? (
          <div className="border hairline rounded-sm py-16 text-center" data-testid="feed-empty">
            <p className="uppercase-label mb-3">Quiet</p>
            <p className="font-serif text-base ink/80 max-w-prose mx-auto">
              No posts yet. Write the first one. The feed updates at 8:30am and 5:30pm Chicago time.
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
