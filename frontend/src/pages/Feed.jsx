import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import Composer from "@/components/Composer";
import PostItem from "@/components/PostItem";
import NextReleaseTimer from "@/components/NextReleaseTimer";
import { useAuth } from "@/context/AuthContext";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

function FeaturedEssay({ essay }) {
  if (!essay) return null;
  const author = essay.author || {};
  const coverUrl = essay.image_path ? `${API}/uploads/file/${essay.image_path}` : null;
  return (
    <Link to={`/essays/${essay.post_id}`} data-testid={`featured-essay-${essay.post_id}`} className="block group border hairline rounded-sm overflow-hidden bg-cream hover:border-gold transition-colors">
      <div className="grid sm:grid-cols-5 gap-0">
        {coverUrl && (
          <div className="sm:col-span-2 h-56 sm:h-auto overflow-hidden border-b sm:border-b-0 sm:border-r hairline">
            <img src={coverUrl} alt="" className="w-full h-full object-cover" />
          </div>
        )}
        <div className={`p-7 sm:p-9 ${coverUrl ? "sm:col-span-3" : "sm:col-span-5"}`}>
          <div className="flex items-center gap-2 mb-3">
            {essay.is_pete_pick && (
              <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete pick</span>
            )}
            <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">. Featured essay</span>
          </div>
          <h2 className="font-display font-semibold text-2xl sm:text-3xl ink leading-tight group-hover:text-gold transition-colors mb-3">
            {essay.title}
          </h2>
          {essay.subtitle && (
            <p className="font-serif italic text-base text-[#2C2410]/75 leading-relaxed mb-4 line-clamp-2">{essay.subtitle}</p>
          )}
          {essay.preview && (
            <p className="prose-serif text-sm text-[#2C2410]/85 leading-relaxed line-clamp-3 mb-4">{essay.preview}</p>
          )}
          <div className="font-sans text-xs text-muted-ink">
            {author.name}{author.market ? ` . ${author.market}` : ""} . {formatDate(essay.release_at || essay.created_at)}
          </div>
        </div>
      </div>
    </Link>
  );
}

function EssayMini({ essay }) {
  const author = essay.author || {};
  return (
    <Link to={`/essays/${essay.post_id}`} data-testid={`mini-essay-${essay.post_id}`} className="block group border hairline rounded-sm p-5 bg-cream hover:border-gold transition-colors">
      {essay.is_pete_pick && (
        <p className="font-sans text-[10px] uppercase tracking-wider text-gold font-semibold mb-2">Pete pick</p>
      )}
      <p className="font-sans text-[10px] uppercase tracking-wider text-muted-ink font-semibold mb-2">Essay</p>
      <h3 className="font-display font-semibold text-base ink leading-snug group-hover:text-gold transition-colors line-clamp-3 mb-3">
        {essay.title}
      </h3>
      <p className="font-sans text-xs text-muted-ink">{author.name}{author.market ? ` . ${author.market}` : ""}</p>
    </Link>
  );
}

export default function Feed() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [shortPosts, setShortPosts] = useState([]);
  const [myPending, setMyPending] = useState([]);
  const [essays, setEssays] = useState([]);
  const [picks, setPicks] = useState([]);
  const [currentPrompt, setCurrentPrompt] = useState(null);
  const [fetching, setFetching] = useState(true);
  const [scope, setScope] = useState(() => localStorage.getItem("feed_scope") || "everyone");

  const load = useCallback(async (currentScope) => {
    setFetching(true);
    try {
      const [feedRes, mineRes, essaysRes, picksRes, promptRes] = await Promise.all([
        api.get(`/posts/feed?scope=${currentScope}`),
        api.get("/posts/mine"),
        api.get("/essays?limit=8"),
        api.get("/posts/picks?limit=4"),
        api.get("/prompts/current").catch(() => ({ data: {} })),
      ]);
      const allFeed = feedRes.data.items || [];
      setShortPosts(allFeed.filter((p) => (p.kind || "post") !== "essay"));
      const pending = (mineRes.data.items || []).filter((p) => p.is_released === false);
      setMyPending(pending);
      setEssays(essaysRes.data.items || []);
      setPicks((picksRes.data.items || []).filter((p) => p.kind === "essay"));
      setCurrentPrompt(promptRes.data && promptRes.data.prompt_id ? promptRes.data : null);
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

  const featured = picks[0] || essays[0];
  const featuredId = featured?.post_id;
  const restEssays = essays.filter((e) => e.post_id !== featuredId).slice(0, 6);

  return (
    <div className="container-wide py-12" data-testid="magazine-feed">
      {/* Masthead */}
      <header className="mb-12 pb-6 border-b hairline flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="uppercase-label mb-2">Today in the room</p>
          <h1 className="font-display font-semibold text-4xl sm:text-5xl ink leading-[1.05]">The Magazine.</h1>
        </div>
        <div className="hidden sm:block"><NextReleaseTimer /></div>
      </header>

      {currentPrompt && (
        <section className="mb-10" data-testid="magazine-prompt">
          <Link to={`/prompts/${currentPrompt.prompt_id}`} className="block border-l-4 border-gold pl-5 pr-4 py-4 bg-cream hover:bg-[#F5EDD6]/50 transition-colors group">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Subject of the week</span>
              <span className="font-sans text-xs text-muted-ink">. {currentPrompt.response_count || 0} {currentPrompt.response_count === 1 ? "response" : "responses"}</span>
            </div>
            <h3 className="font-display font-semibold text-xl ink leading-snug group-hover:text-gold transition-colors">{currentPrompt.title}</h3>
            {currentPrompt.body && (
              <p className="font-serif text-sm text-[#2C2410]/75 leading-relaxed mt-1 line-clamp-2">{currentPrompt.body}</p>
            )}
          </Link>
        </section>
      )}

      {fetching && !featured ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : (
        <>
          {/* Featured + Pete picks rail */}
          <section className="grid lg:grid-cols-3 gap-8 mb-16" data-testid="magazine-top">
            <div className="lg:col-span-2">
              {featured ? <FeaturedEssay essay={featured} /> : (
                <div className="border hairline rounded-sm py-16 px-8 text-center bg-cream">
                  <p className="uppercase-label mb-3">Quiet</p>
                  <p className="font-serif text-base ink/80 max-w-prose mx-auto">
                    No essays published yet. <Link to="/write" className="text-gold underline underline-offset-4 decoration-gold-mid">Write the first one.</Link>
                  </p>
                </div>
              )}
            </div>
            <aside data-testid="magazine-picks">
              <div className="flex items-center gap-2 mb-4">
                <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Pete recommends</span>
                <span className="h-px flex-1 bg-gold-mid" />
              </div>
              {picks.length === 0 ? (
                <p className="font-serif text-sm text-muted-ink italic">Pete has not picked anything this week.</p>
              ) : (
                <div className="space-y-4">
                  {picks.slice(0, 4).map((p) => (
                    <Link key={p.post_id} to={`/essays/${p.post_id}`} data-testid={`magazine-pick-${p.post_id}`} className="block group">
                      <h4 className="font-display font-semibold text-base ink leading-snug group-hover:text-gold transition-colors line-clamp-2 mb-1">
                        {p.title}
                      </h4>
                      <p className="font-sans text-xs text-muted-ink">{p.author?.name}{p.author?.market ? ` . ${p.author.market}` : ""}</p>
                    </Link>
                  ))}
                </div>
              )}
            </aside>
          </section>

          {/* Recent essays grid */}
          {restEssays.length > 0 && (
            <section className="mb-16" data-testid="magazine-grid">
              <div className="flex items-end justify-between mb-6">
                <h2 className="font-display font-semibold text-2xl ink">Recent essays</h2>
                <Link to="/essays" data-testid="see-all-essays" className="font-sans text-xs uppercase tracking-wider text-gold font-semibold hover:opacity-80">See all</Link>
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {restEssays.map((e) => <EssayMini key={e.post_id} essay={e} />)}
              </div>
            </section>
          )}

          {/* Short post composer + stream */}
          <section className="grid lg:grid-cols-3 gap-12" data-testid="magazine-stream">
            <div className="lg:col-span-2">
              <div className="mb-8">
                <p className="uppercase-label mb-2">The room</p>
                <h2 className="font-display font-semibold text-2xl ink">Short notes from working operators.</h2>
              </div>

              <Composer onPosted={() => load(scope)} />

              {myPending.length > 0 && (
                <section className="mt-10" data-testid="my-pending-section">
                  <p className="uppercase-label mb-4">Your queue</p>
                  <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
                    {myPending.map((p) => (
                      <div key={p.post_id} data-testid={`pending-${p.post_id}`} className="px-5 py-4 flex items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <p className="font-serif text-[15px] ink leading-relaxed line-clamp-3">{p.text || p.title}</p>
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
                ) : shortPosts.length === 0 ? (
                  <div className="border hairline rounded-sm py-16 text-center" data-testid="feed-empty">
                    <p className="uppercase-label mb-3">Quiet</p>
                    <p className="font-serif text-base ink/80 max-w-prose mx-auto">
                      {scope === "following" ? "No released posts from people you follow yet. Switch to Everyone to see the full room." : "No posts released yet. Write the first one. The feed updates at 8:30am and 5:30pm Chicago time."}
                    </p>
                  </div>
                ) : (
                  <div>
                    {shortPosts.map((p) => <PostItem key={p.post_id} post={p} />)}
                  </div>
                )}
              </div>
            </div>

            <aside className="hidden lg:block">
              <div className="sticky top-24 space-y-8">
                <div className="border hairline rounded-sm p-5 bg-cream">
                  <p className="uppercase-label mb-3">From your desk</p>
                  <p className="font-serif text-sm ink/80 leading-relaxed mb-4">
                    Sit down and write. Drafts auto-save. Short posts batch at 8:30am and 5:30pm CT.
                  </p>
                  <Link to="/write" data-testid="aside-write-link" className="inline-block bg-gold text-cream font-sans font-semibold text-xs px-4 py-2 rounded-sm hover:opacity-90 transition-opacity uppercase tracking-wide">
                    Open your desk
                  </Link>
                </div>
                <div className="border hairline rounded-sm p-5 bg-cream">
                  <p className="uppercase-label mb-3">Saved for later</p>
                  <p className="font-serif text-sm ink/80 leading-relaxed mb-4">
                    Bookmark essays from any reader. Your library is private.
                  </p>
                  <Link to="/library" data-testid="aside-library-link" className="font-sans text-xs uppercase tracking-wider text-gold font-semibold hover:opacity-80">
                    Open library
                  </Link>
                </div>
              </div>
            </aside>
          </section>
        </>
      )}
    </div>
  );
}
