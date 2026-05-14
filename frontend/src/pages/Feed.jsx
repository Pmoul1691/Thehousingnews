import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import PostItem from "@/components/PostItem";
import FeedCompose from "@/components/FeedCompose";
import NextReleaseTimer from "@/components/NextReleaseTimer";
import { useAuth } from "@/context/AuthContext";

function PendingChip({ post }) {
  const formatLocal = (iso) => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" })
        .format(d)
        .toLowerCase()
        .replace(" ", "");
    } catch { return ""; }
  };
  return (
    <div data-testid={`pending-${post.post_id}`} className="py-3 flex items-start gap-3 border-b hairline last:border-b-0">
      <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm shrink-0 mt-0.5">Queued</span>
      <p className="font-serif text-sm ink leading-snug line-clamp-2 flex-1">{post.text || post.title}</p>
      <span className="font-sans text-[11px] text-muted-ink whitespace-nowrap mt-0.5">{formatLocal(post.release_at)} CT</span>
    </div>
  );
}

export default function Feed() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [stream, setStream] = useState([]); // essays + short posts mixed, sorted by release_at desc
  const [myPending, setMyPending] = useState([]);
  const [picks, setPicks] = useState([]);
  const [currentPrompt, setCurrentPrompt] = useState(null);
  const [fetching, setFetching] = useState(true);
  const [scope, setScope] = useState(() => localStorage.getItem("feed_scope") || "everyone");

  const load = useCallback(async (currentScope) => {
    setFetching(true);
    try {
      // /api/posts/feed already returns both essays + short posts, scope-filtered
      const [feedRes, mineRes, picksRes, promptRes, profRes] = await Promise.all([
        api.get(`/posts/feed?scope=${currentScope}`),
        api.get("/posts/mine"),
        api.get("/posts/picks?limit=4"),
        api.get("/prompts/current").catch(() => ({ data: {} })),
        api.get("/profile").catch(() => ({ data: {} })),
      ]);
      const items = feedRes.data.items || [];
      // Sort defensively in case the backend orders different kinds independently
      const mixed = items.slice().sort((a, b) => {
        const at = new Date(a.release_at || a.created_at).getTime();
        const bt = new Date(b.release_at || b.created_at).getTime();
        return bt - at;
      });
      setStream(mixed);
      const pending = (mineRes.data.items || []).filter((p) => p.is_released === false);
      setMyPending(pending);
      setPicks(picksRes.data.items || []);
      setCurrentPrompt(promptRes.data && promptRes.data.prompt_id ? promptRes.data : null);
      setProfile(profRes.data || null);
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

  const firstName = (user?.name || "").split(" ")[0] || "there";

  return (
    <div className="container-wide py-10" data-testid="magazine-feed">
      <div className="grid lg:grid-cols-3 gap-10">
        {/* Main column */}
        <div className="lg:col-span-2 min-w-0">
          {/* Greeting + scope toggle - calm header, FB-style */}
          <header className="mb-6 flex items-end justify-between flex-wrap gap-4">
            <div>
              <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-gold mb-1">The room</p>
              <h1 data-testid="feed-greeting" className="font-display font-semibold text-2xl sm:text-3xl ink leading-tight">
                Good day, {firstName}.
              </h1>
            </div>
            <div className="sm:hidden"><NextReleaseTimer /></div>
          </header>

          {/* Compose (collapsed by default, expands on click) */}
          <FeedCompose user={user} profile={profile} onPosted={() => load(scope)} />

          {/* Subject of the week - thin hairline-only row, no colored box */}
          {currentPrompt && (
            <Link
              to={`/prompts/${currentPrompt.prompt_id}`}
              data-testid="feed-prompt-row"
              className="block py-4 border-b hairline group"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Subject of the week</span>
                <span className="font-sans text-xs text-muted-ink">· {currentPrompt.response_count || 0} {currentPrompt.response_count === 1 ? "response" : "responses"}</span>
              </div>
              <h3 className="font-display font-semibold text-base ink leading-snug group-hover:text-gold transition-colors">{currentPrompt.title}</h3>
            </Link>
          )}

          {/* Queued posts - tiny stack so the writer can see what is coming */}
          {myPending.length > 0 && (
            <section className="mt-8" data-testid="my-pending-section">
              <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">Your queue</p>
              <div>
                {myPending.map((p) => <PendingChip key={p.post_id} post={p} />)}
              </div>
            </section>
          )}

          {/* Scope tabs */}
          <div className="mt-10 flex items-center gap-6 border-b hairline">
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

          {/* Main stream - mixed essays + shorts, chronological */}
          <div className="mt-6" data-testid="feed-stream">
            {fetching && stream.length === 0 ? (
              <div className="font-serif italic text-base text-muted-ink py-16 text-center">Loading.</div>
            ) : stream.length === 0 ? (
              <div className="py-20 text-center" data-testid="feed-empty">
                <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">Quiet</p>
                <p className="font-serif italic text-base text-[#2C2410]/65 max-w-prose mx-auto">
                  {scope === "following" ? "No released posts from people you follow yet. Switch to Everyone to see the full room." : "No posts released yet. Write the first one."}
                </p>
              </div>
            ) : (
              stream.map((p) =>
                p.kind === "essay"
                  ? <PostItem key={p.post_id} post={p} onChange={() => load(scope)} />
                  : <PostItem key={p.post_id} post={p} onChange={() => load(scope)} />
              )
            )}
          </div>
        </div>

        {/* Right rail - quiet, no boxes, hairline only */}
        <aside className="hidden lg:block">
          <div className="sticky top-24 space-y-10">
            <div className="hidden sm:block"><NextReleaseTimer /></div>

            {picks.length > 0 && (
              <div data-testid="rail-picks">
                <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Staff picks</p>
                <div className="divide-y divide-[#E8D4A0]/60">
                  {picks.slice(0, 3).map((p) => (
                    <div key={p.post_id} className="py-3 first:pt-0">
                      <Link to={p.kind === "essay" ? `/essays/${p.post_id}` : `/feed`} data-testid={`rail-pick-${p.post_id}`} className="block group">
                        <h4 className="font-display font-semibold text-sm ink leading-snug group-hover:text-gold transition-colors line-clamp-2 mb-1">
                          {p.title || (p.text || "").slice(0, 90)}
                        </h4>
                        <p className="font-sans text-[11px] text-muted-ink">{p.author?.name}</p>
                      </Link>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div data-testid="rail-shortcuts">
              <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">Shortcuts</p>
              <div className="flex flex-col gap-2">
                <Link to="/essays" data-testid="rail-link-essays" className="font-sans text-sm ink hover:text-gold transition-colors">Browse all essays</Link>
                <Link to="/members" data-testid="rail-link-members" className="font-sans text-sm ink hover:text-gold transition-colors">See members</Link>
                <Link to="/library" data-testid="rail-link-library" className="font-sans text-sm ink hover:text-gold transition-colors">Your library</Link>
                <Link to="/prompts" data-testid="rail-link-prompts" className="font-sans text-sm ink hover:text-gold transition-colors">Past subjects</Link>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
