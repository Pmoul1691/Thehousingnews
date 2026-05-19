import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Comprehensive Admin Overview — single page summarizing the platform.
 *
 * Sections (each in its own card, minimalist UI):
 *   1. Members (counts + 7d signups)
 *   2. Application queue (counts + jump)
 *   3. Brevo invites (sent / claimed / pending / expiring)
 *   4. Daily Brief health (morning + evening sends, opens, clicks) + send/preview
 *   5. Recent post activity (last 20)
 *   6. Trending tags (top 20)
 *   7. Top members (most-published last 30d)
 *   8. Feed health (every publisher's last fetch + error_count)
 *   9. Quick actions row (refresh RSS, run briefs, etc.)
 *  10. PATs counts
 *
 * Designed to be functional first, dense but readable. All numbers come from
 * a single GET /api/admin/dashboard/overview call so the page loads in one
 * round trip.
 */
const fmt = (n) => (n ?? 0).toLocaleString();
const pct = (n) => `${Math.round((n || 0) * 100)}%`;

function StatTile({ label, value, hint, testid, accent = false }) {
  return (
    <div
      data-testid={testid}
      className={`bg-white border ${accent ? "border-gold" : "border-gold/15"} rounded-sm p-4`}
    >
      <p className="font-sans text-[10px] uppercase tracking-[0.2em] font-semibold text-gold mb-1.5">
        {label}
      </p>
      <p className="font-display font-semibold text-2xl ink leading-none">{value}</p>
      {hint && <p className="font-sans text-[11px] text-muted-ink mt-2 leading-relaxed">{hint}</p>}
    </div>
  );
}

function PanelHeader({ children, right }) {
  return (
    <div className="flex items-baseline justify-between mb-3 gap-3 flex-wrap">
      <h3 className="font-display font-semibold text-lg ink tracking-tight">{children}</h3>
      {right}
    </div>
  );
}

function Panel({ children, testid, className = "" }) {
  return (
    <section
      data-testid={testid}
      className={`bg-cream-soft border border-gold/15 rounded-sm p-5 ${className}`}
    >
      {children}
    </section>
  );
}

function QuickActions({ onReload }) {
  const [busy, setBusy] = useState(null);

  const run = async (key, fn, success) => {
    setBusy(key);
    try {
      await fn();
      toast.success(success);
      if (onReload) await onReload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Action failed");
    } finally { setBusy(null); }
  };

  const sendBrief = (kind) => run(
    `send-${kind}`,
    () => api.post(`/admin/briefings/send?kind=${kind}`),
    `${kind === "morning" ? "Morning" : "Evening"} brief dispatched`,
  );

  const previewBrief = async (kind) => {
    setBusy(`preview-${kind}`);
    try {
      const r = await api.get(`/admin/briefings/preview?kind=${kind}`);
      const articleCount = (r.data.articles || []).length;
      // Open the preview as a Blob URL so the new tab renders the JSON as
      // pre-formatted text without any HTML parsing. document.write was a
      // classic XSS sink — Blob URLs are sandboxed to a single document.
      const pretty = JSON.stringify(r.data, null, 2);
      const blob = new Blob([pretty], { type: "text/plain; charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (!w) {
        toast.success(`Preview ready: ${articleCount} articles, ${r.data.recipients_total} recipients`);
      }
      // Release the object URL after the tab has had time to load it.
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Preview failed");
    } finally { setBusy(null); }
  };

  const refreshRss = () => run(
    "rss",
    async () => {
      // Manual admin refresh — uses the same in-process ingest as the cron.
      // The token-protected /api/refresh-feeds endpoint exists for external
      // cron services; admins go through the session-authed admin route.
      await api.post("/admin/rss/import");
    },
    "Essay/Substack import kicked off",
  );

  return (
    <div className="flex flex-wrap gap-2" data-testid="admin-quick-actions">
      <button type="button" onClick={() => sendBrief("morning")} disabled={busy} data-testid="admin-send-morning-brief" className="font-sans text-xs uppercase tracking-wider font-semibold bg-ink text-cream px-3 py-1.5 rounded-sm hover:bg-gold transition-colors disabled:opacity-50">
        {busy === "send-morning" ? "Sending…" : "Send morning brief"}
      </button>
      <button type="button" onClick={() => sendBrief("evening")} disabled={busy} data-testid="admin-send-evening-brief" className="font-sans text-xs uppercase tracking-wider font-semibold bg-ink text-cream px-3 py-1.5 rounded-sm hover:bg-gold transition-colors disabled:opacity-50">
        {busy === "send-evening" ? "Sending…" : "Send evening brief"}
      </button>
      <button type="button" onClick={() => previewBrief("morning")} disabled={busy} data-testid="admin-preview-morning" className="font-sans text-xs uppercase tracking-wider font-semibold border border-gold text-gold px-3 py-1.5 rounded-sm hover:bg-gold hover:text-cream transition-colors disabled:opacity-50">
        Preview morning
      </button>
      <button type="button" onClick={() => previewBrief("evening")} disabled={busy} data-testid="admin-preview-evening" className="font-sans text-xs uppercase tracking-wider font-semibold border border-gold text-gold px-3 py-1.5 rounded-sm hover:bg-gold hover:text-cream transition-colors disabled:opacity-50">
        Preview evening
      </button>
      <button type="button" onClick={refreshRss} disabled={busy} data-testid="admin-refresh-rss" className="font-sans text-xs uppercase tracking-wider font-semibold border border-gold text-gold px-3 py-1.5 rounded-sm hover:bg-gold hover:text-cream transition-colors disabled:opacity-50">
        {busy === "rss" ? "Running…" : "Import substacks"}
      </button>
    </div>
  );
}

export default function AdminOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/dashboard/overview");
      setData(r.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load dashboard");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return <p className="text-muted-ink py-12 font-sans" data-testid="admin-overview-loading">Loading dashboard…</p>;
  }
  if (!data) return null;

  const d = data;

  return (
    <div className="space-y-8" data-testid="admin-overview">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Operator</p>
          <h1 className="font-display font-semibold text-3xl ink mt-1 tracking-tight">Dashboard.</h1>
          <p className="font-sans text-[12px] text-muted-ink mt-1">
            Updated {new Date(d.generated_at).toLocaleTimeString()}.{" "}
            <button type="button" onClick={load} className="text-gold hover:underline" data-testid="admin-overview-refresh">Refresh</button>
          </p>
        </div>
        <QuickActions onReload={load} />
      </div>

      {/* Members + Apps + Invites */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3" data-testid="admin-stat-grid">
        <StatTile label="Approved" value={fmt(d.members.approved)} hint="All members are free" testid="stat-members-approved" />
        <StatTile label="Invited" value={fmt(d.members.invited)} hint="Pending profile" testid="stat-members-invited" />
        <StatTile label="New 7d" value={fmt(d.members.new_7d)} hint="Joined this week" accent testid="stat-members-new" />
        <StatTile label="Suspended" value={fmt(d.members.suspended)} testid="stat-members-suspended" />
        <StatTile label="Pending apps" value={fmt(d.applications.pending)} hint={`${d.applications.approved} approved · ${d.applications.declined} declined`} testid="stat-apps-pending" />
        <StatTile label="PATs (live)" value={fmt(d.pats.live)} hint={`${d.pats.revoked} revoked`} testid="stat-pats" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Brief health */}
        <Panel testid="admin-briefs-panel">
          <PanelHeader right={<span className="font-mono text-[10px] text-muted-ink">last 30 days</span>}>
            Daily Brief health
          </PanelHeader>
          <div className="grid grid-cols-2 gap-3">
            {["morning", "evening"].map((k) => {
              const b = d.briefs[k];
              return (
                <div key={k} className="bg-white border border-gold/15 rounded-sm p-4" data-testid={`brief-${k}-card`}>
                  <p className="font-sans text-[10px] uppercase tracking-[0.2em] font-semibold text-gold mb-2">
                    {k} brief — {k === "morning" ? "7:30 AM" : "5:30 PM"} CT
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="font-display text-xl ink">{fmt(b.sent)}</div>
                      <div className="font-mono text-[9px] uppercase tracking-wider text-muted-ink">sent</div>
                    </div>
                    <div>
                      <div className="font-display text-xl ink">{pct(b.open_rate)}</div>
                      <div className="font-mono text-[9px] uppercase tracking-wider text-muted-ink">opens</div>
                    </div>
                    <div>
                      <div className="font-display text-xl ink">{pct(b.click_rate)}</div>
                      <div className="font-mono text-[9px] uppercase tracking-wider text-muted-ink">clicks</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>

        {/* Brevo invites */}
        <Panel testid="admin-invites-panel">
          <PanelHeader right={<Link to="/admin?section=invite" className="font-mono text-[10px] text-gold hover:underline">Manage →</Link>}>
            Invites
          </PanelHeader>
          <div className="grid grid-cols-4 gap-3">
            <StatTile label="Total" value={fmt(d.invites.total)} testid="stat-invites-total" />
            <StatTile label="Claimed" value={fmt(d.invites.claimed)} testid="stat-invites-claimed" />
            <StatTile label="Pending" value={fmt(d.invites.pending)} testid="stat-invites-pending" />
            <StatTile label="Expiring 7d" value={fmt(d.invites.expiring_7d)} accent testid="stat-invites-expiring" />
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Feed health */}
        <Panel testid="admin-feed-panel" className="overflow-hidden">
          <PanelHeader right={<span className="font-mono text-[10px] text-muted-ink">{d.feed_health.active} active · {d.feed_health.failing} failing</span>}>
            Feed health
          </PanelHeader>
          <div className="max-h-[420px] overflow-y-auto -mx-5 px-5" data-testid="admin-feed-list">
            <table className="w-full text-sm">
              <thead>
                <tr className="font-mono text-[10px] uppercase tracking-wider text-muted-ink border-b border-gold/20">
                  <th className="text-left py-2 pr-2">Publisher</th>
                  <th className="text-left py-2 pr-2">Cat</th>
                  <th className="text-left py-2 pr-2">Last</th>
                  <th className="text-left py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {d.feed_health.publishers.map((p) => {
                  const failing = (p.error_count || 0) > 0;
                  return (
                    <tr key={p.id} data-testid={`feed-row-${p.slug}`} className="border-b border-gold/10 hover:bg-white/50">
                      <td className="py-1.5 pr-2">
                        <span className="font-sans text-[12px] ink font-medium">{p.name}</span>
                        {!p.active && <span className="ml-1.5 font-mono text-[9px] text-muted-ink">(off)</span>}
                      </td>
                      <td className="py-1.5 pr-2 font-mono text-[10px] text-muted-ink">{p.category}</td>
                      <td className="py-1.5 pr-2 font-mono text-[10px] text-muted-ink">
                        {p.last_fetched_at ? new Date(p.last_fetched_at).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"}) : "—"}
                      </td>
                      <td className="py-1.5">
                        {failing ? (
                          <span className="font-mono text-[10px] bg-deepred/10 text-deepred px-1.5 py-0.5 rounded-sm" title={p.last_fetch_status}>
                            {p.last_fetch_status?.slice(0, 24) || "error"} · {p.error_count}
                          </span>
                        ) : (
                          <span className="font-mono text-[10px] text-emerald-700">ok</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Top members */}
        <Panel testid="admin-top-members-panel">
          <PanelHeader right={<span className="font-mono text-[10px] text-muted-ink">last 30 days</span>}>
            Top members
          </PanelHeader>
          <ol className="space-y-2" data-testid="admin-top-members-list">
            {d.top_members.length === 0 && (
              <li className="font-serif italic text-muted-ink text-sm">No member posts in the last 30 days.</li>
            )}
            {d.top_members.map((m, i) => (
              <li key={m.user_id} data-testid={`top-member-${m.user_id}`} className="flex items-center gap-3 bg-white border border-gold/10 rounded-sm px-3 py-2">
                <span className="font-mono text-[11px] text-gold/70 w-6">{i + 1}.</span>
                <div className="flex-1 min-w-0">
                  <Link to={`/profile/${m.user_id}`} className="font-display font-semibold text-[13px] ink hover:text-gold">{m.name || "Unknown"}</Link>
                  {m.market && <p className="font-sans text-[10px] uppercase tracking-wider text-muted-ink">{m.market}</p>}
                </div>
                <span className="font-mono text-[11px] text-ink">{m.posts}</span>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trending tags */}
        <Panel testid="admin-tags-panel">
          <PanelHeader right={<span className="font-mono text-[10px] text-muted-ink">last 30 days</span>}>
            Trending tags
          </PanelHeader>
          <div className="flex flex-wrap gap-2" data-testid="admin-tag-cloud">
            {d.trending_tags.length === 0 ? (
              <p className="font-serif italic text-muted-ink text-sm">No tagged posts yet.</p>
            ) : d.trending_tags.map((t) => (
              <Link
                key={t.tag}
                to={`/tag/${encodeURIComponent(t.tag)}`}
                data-testid={`admin-tag-${t.tag}`}
                className="font-display font-semibold text-[13px] bg-white border border-gold/20 px-2.5 py-1 rounded-full hover:border-gold transition-colors"
              >
                #{t.tag} <span className="font-mono text-[10px] text-gold/70">{t.count}</span>
              </Link>
            ))}
          </div>
        </Panel>

        {/* Recent posts */}
        <Panel testid="admin-recent-posts-panel" className="lg:col-span-2">
          <PanelHeader right={<span className="font-mono text-[10px] text-muted-ink">last {d.recent_posts.length}</span>}>
            Recent post activity
          </PanelHeader>
          <ul className="space-y-2 max-h-[420px] overflow-y-auto -mx-5 px-5" data-testid="admin-recent-posts-list">
            {d.recent_posts.length === 0 && (
              <li className="font-serif italic text-muted-ink text-sm">No posts yet.</li>
            )}
            {d.recent_posts.map((p) => {
              const blurb = (p.title || p.text || "").trim().slice(0, 120);
              return (
                <li key={p.post_id} data-testid={`admin-recent-${p.post_id}`} className="flex items-start gap-3 bg-white border border-gold/10 rounded-sm px-3 py-2">
                  <span className={`font-mono text-[9px] uppercase px-1.5 py-0.5 rounded-sm shrink-0 mt-0.5 ${
                    p.status === "approved" ? "bg-emerald-50 text-emerald-800" :
                    p.status === "pending_release" ? "bg-amber-50 text-amber-800" :
                    p.status === "flagged" ? "bg-deepred/10 text-deepred" : "bg-cream-soft text-muted-ink"
                  }`}>
                    {p.status?.split("_")[0]}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-display font-semibold text-[13px] ink line-clamp-1">{blurb || "(empty)"}</p>
                    <p className="font-sans text-[10px] text-muted-ink mt-0.5">
                      {p.kind} · {p.author?.name || "Unknown"} {p.author?.market ? `· ${p.author.market}` : ""} · {new Date(p.created_at).toLocaleString()}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
