import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import Composer from "@/components/Composer";
import { useAuth } from "@/context/AuthContext";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

function formatDateTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

function SlimStat({ label, value, last }) {
  return (
    <div data-testid={`write-stat-${label.toLowerCase().replace(/\s+/g, "-")}`} className={`flex-1 min-w-[120px] px-4 py-3 ${last ? "" : "border-r border-gold/10"}`}>
      <p className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-ink mb-1">{label}</p>
      <p className="font-display font-semibold text-2xl ink leading-none">{value}</p>
    </div>
  );
}

export default function Write() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [published, setPublished] = useState([]);
  const [scheduled, setScheduled] = useState([]);
  const [tab, setTab] = useState("published");
  const [showComposer, setShowComposer] = useState(false);

  const reload = useCallback(async () => {
    const [s, p, sc] = await Promise.all([
      api.get("/me/writer/stats"),
      api.get("/me/writer/published"),
      api.get("/me/writer/scheduled"),
    ]);
    setStats(s.data);
    setPublished(p.data.items || []);
    setScheduled(sc.data.items || []);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    reload();
  }, [user, loading, navigate, reload]);

  if (loading || !stats) {
    return <div className="container-prose py-24 text-center font-serif text-muted-ink">Loading.</div>;
  }

  return (
    <div className="container-wide py-12 max-w-5xl mx-auto" data-testid="write-dashboard-container">
      <div className="mb-8 flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="uppercase-label mb-2">Your desk</p>
          <h1 className="font-display font-semibold text-4xl ink leading-tight">Write.</h1>
          <p className="font-serif text-base text-muted-ink mt-3 max-w-2xl">
            Long-form essays and short posts, in one place. Drafts auto-save. Schedule essays for later or publish now and send to your followers.
          </p>
        </div>
        <button
          data-testid="new-essay-button"
          onClick={() => setShowComposer((s) => !s)}
          className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-full hover:opacity-90 transition-opacity"
        >
          {showComposer ? "Hide composer" : "New essay"}
        </button>
      </div>

      {/* Slim stats row */}
      <div
        className="flex flex-wrap md:flex-nowrap mb-10 bg-white/60 border border-gold/20 rounded-2xl shadow-sm"
        data-testid="stats-summary-row"
      >
        <SlimStat label="Published" value={stats.published_essays} />
        <SlimStat label="Scheduled" value={stats.scheduled_essays} />
        <SlimStat label="Short posts" value={stats.short_posts_30d} />
        <SlimStat label="Followers" value={stats.follower_count} />
        <SlimStat label="Emails sent" value={stats.essay_emails_sent_30d} last />
      </div>

      {showComposer && (
        <div className="mb-12" data-testid="write-composer">
          <Composer onPosted={reload} />
          {stats.has_draft && (
            <p className="font-sans text-xs text-muted-ink mt-2 italic" data-testid="write-draft-indicator">
              You have an existing draft. It is loaded above.
            </p>
          )}
        </div>
      )}

      {/* Dashboard tabs (Substack-style underline) */}
      <div className="border-b border-gold/20 flex items-center gap-8 mb-6">
        {[
          { k: "published", l: `Published`, n: published.length },
          { k: "scheduled", l: `Scheduled`, n: scheduled.length },
        ].map((t) => (
          <button
            key={t.k}
            data-testid={`write-tab-${t.k}`}
            onClick={() => setTab(t.k)}
            className={`pb-3 font-sans text-sm font-medium transition-colors flex items-center gap-2 ${tab === t.k ? "text-ink border-b-2 border-gold -mb-px" : "text-muted-ink hover:text-ink"}`}
          >
            <span>{t.l}</span>
            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${tab === t.k ? "bg-gold/10 text-gold" : "bg-ink/5 text-muted-ink"}`}>
              {t.n}
            </span>
          </button>
        ))}
      </div>

      {tab === "published" && (
        published.length === 0 ? (
          <div className="border hairline rounded-sm py-16 text-center" data-testid="write-published-empty">
            <p className="uppercase-label mb-3">Nothing yet</p>
            <p className="font-serif text-base ink/80 max-w-prose mx-auto">
              You have not published an essay. Click New essay above to write your first one.
            </p>
          </div>
        ) : (
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="write-published-list">
            {published.map((p) => {
              const coverUrl = p.image_path ? `${API}/uploads/file/${p.image_path}` : null;
              return (
                <div key={p.post_id} data-testid={`write-published-${p.post_id}`} className="p-5 flex gap-4 items-start">
                  {coverUrl && (
                    <div className="hidden sm:block w-20 h-20 shrink-0 border hairline rounded-sm overflow-hidden">
                      <img src={coverUrl} alt="" className="w-full h-full object-cover" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <Link to={`/essays/${p.post_id}`} className="block group">
                      <h3 className="font-display font-semibold text-lg ink leading-snug group-hover:text-gold transition-colors mb-1">
                        {p.title || "Untitled"}
                      </h3>
                      {p.subtitle && (
                        <p className="font-serif italic text-sm text-[#2C2410]/75 line-clamp-1 mb-2">{p.subtitle}</p>
                      )}
                    </Link>
                    <div className="font-sans text-xs text-muted-ink flex items-center gap-3 flex-wrap">
                      <span>Published {formatDate(p.release_at)}</span>
                      <span>.</span>
                      <span>{p.emails_sent || 0} emails sent</span>
                      {p.is_pete_pick && <><span>.</span><span className="text-gold font-semibold uppercase tracking-wider">Staff pick</span></>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )
      )}

      {tab === "scheduled" && (
        scheduled.length === 0 ? (
          <div className="border hairline rounded-sm py-16 text-center" data-testid="write-scheduled-empty">
            <p className="uppercase-label mb-3">No queue</p>
            <p className="font-serif text-base ink/80 max-w-prose mx-auto">
              You have no scheduled essays. Use the schedule field in the composer to queue one for later.
            </p>
          </div>
        ) : (
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="write-scheduled-list">
            {scheduled.map((p) => (
              <div key={p.post_id} data-testid={`write-scheduled-${p.post_id}`} className="p-5 flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <h3 className="font-display font-semibold text-lg ink leading-snug mb-1">{p.title || "Untitled"}</h3>
                  {p.subtitle && (
                    <p className="font-serif italic text-sm text-[#2C2410]/75 line-clamp-1 mb-2">{p.subtitle}</p>
                  )}
                  <div className="font-sans text-xs text-muted-ink">
                    Publishes {formatDateTime(p.release_at)} CT
                  </div>
                </div>
                <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm">Queued</span>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
