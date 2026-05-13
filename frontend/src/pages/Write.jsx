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

function StatCard({ label, value, hint }) {
  return (
    <div className="border hairline rounded-sm p-5 bg-cream">
      <p className="uppercase-label mb-2">{label}</p>
      <p className="font-display font-semibold text-3xl ink leading-none">{value}</p>
      {hint && <p className="font-sans text-xs text-muted-ink mt-2">{hint}</p>}
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
    <div className="container-wide py-12" data-testid="write-page">
      <div className="mb-10 flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="uppercase-label mb-2">Your desk</p>
          <h1 className="font-display font-semibold text-4xl ink leading-tight">Write.</h1>
          <p className="font-serif text-base text-muted-ink mt-3 max-w-2xl">
            Long-form essays and short posts, in one place. Drafts auto-save. Schedule essays for later or publish now and send to your followers.
          </p>
        </div>
        <button
          data-testid="write-new-essay-btn"
          onClick={() => setShowComposer((s) => !s)}
          className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:opacity-90 transition-opacity"
        >
          {showComposer ? "Hide composer" : "New essay"}
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-12" data-testid="write-stats">
        <StatCard label="Published" value={stats.published_essays} hint="Essays released" />
        <StatCard label="Scheduled" value={stats.scheduled_essays} hint="Queued essays" />
        <StatCard label="Short posts" value={stats.short_posts_30d} hint="Last 30 days" />
        <StatCard label="Followers" value={stats.follower_count} hint="Receive your essays" />
        <StatCard label="Emails sent" value={stats.essay_emails_sent_30d} hint="Last 30 days" />
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

      <div className="border-b hairline flex items-center gap-6 mb-8">
        {[
          { k: "published", l: `Published (${published.length})` },
          { k: "scheduled", l: `Scheduled (${scheduled.length})` },
        ].map((t) => (
          <button
            key={t.k}
            data-testid={`write-tab-${t.k}`}
            onClick={() => setTab(t.k)}
            className={`pb-3 font-sans text-sm font-medium transition-colors ${tab === t.k ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
          >
            {t.l}
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
                      {p.is_pete_pick && <><span>.</span><span className="text-gold font-semibold uppercase tracking-wider">Pete pick</span></>}
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
