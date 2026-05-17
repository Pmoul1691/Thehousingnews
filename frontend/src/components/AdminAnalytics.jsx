import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Site analytics dashboard — four areas:
 *   1. Acquisition (member growth + signup funnel)
 *   2. Engagement (active members, content created, top contributors)
 *   3. Retention (at-risk, churn proxy)
 *   4. Traffic (pageviews + top paths, populated by /api/events/pageview)
 *
 * All data is read-only — admins can't fudge the numbers.
 */

function StatTile({ label, value, hint, testid, tone = "neutral" }) {
  const toneClass = {
    neutral: "border-gold/15",
    ok: "border-emerald-700/30",
    warn: "border-deepred/40",
    accent: "border-gold/50",
  }[tone];
  return (
    <div data-testid={testid} className={`bg-cream-soft border ${toneClass} rounded-sm p-4`}>
      <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink">{label}</p>
      <p className="font-display font-semibold text-3xl ink mt-1.5">{value ?? "—"}</p>
      {hint ? <p className="font-serif italic text-xs text-muted-ink mt-1">{hint}</p> : null}
    </div>
  );
}

function Section({ title, subtitle, children, testid }) {
  return (
    <section data-testid={testid} className="space-y-3">
      <header className="flex items-baseline justify-between gap-3 flex-wrap border-b border-gold/15 pb-1.5">
        <h2 className="font-display font-semibold text-lg ink">{title}</h2>
        {subtitle ? <p className="font-serif italic text-xs text-muted-ink">{subtitle}</p> : null}
      </header>
      {children}
    </section>
  );
}

function BarChart({ rows, getValue, getLabel, color = "bg-gold", testid }) {
  if (!rows?.length) {
    return <p className="font-serif italic text-sm text-muted-ink py-6 text-center">No data yet.</p>;
  }
  const max = Math.max(1, ...rows.map((r) => getValue(r) || 0));
  return (
    <div className="flex items-end gap-2 h-32" data-testid={testid}>
      {rows.map((r, i) => {
        const v = getValue(r) || 0;
        const pct = Math.round(100 * v / max);
        const label = getLabel(r);
        return (
          <div key={label + i} className="flex-1 flex flex-col items-center min-w-0" title={`${label}: ${v}`}>
            <div className="w-full h-full flex flex-col justify-end">
              <div className={`w-full rounded-t-sm ${color}`} style={{ height: `${pct}%` }} />
            </div>
            <span className="font-mono text-[8px] text-muted-ink mt-1 truncate w-full text-center">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function AdminAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/site-analytics");
      setData(r.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load analytics");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <p className="font-serif italic text-sm text-muted-ink py-12 text-center">Loading analytics.</p>;
  if (!data) return null;

  const a = data.acquisition;
  const e = data.engagement;
  const r = data.retention;
  const t = data.traffic;

  return (
    <div className="space-y-8" data-testid="admin-analytics">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink">
          As of {new Date(data.as_of).toLocaleString()}
        </p>
        <button
          type="button"
          onClick={load}
          className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold hover:underline"
          data-testid="analytics-refresh"
        >
          Refresh
        </button>
      </div>

      {/* ─── ACQUISITION ─────────────────────────────────────────── */}
      <Section title="Acquisition" subtitle="Who's coming in and from where" testid="analytics-acquisition">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile testid="acq-total" label="Total members" value={a.total_members} tone="accent" hint="Approved" />
          <StatTile testid="acq-new-7d" label="New · 7d" value={a.new_7d} />
          <StatTile testid="acq-new-30d" label="New · 30d" value={a.new_30d} />
          <StatTile testid="acq-new-90d" label="New · 90d" value={a.new_90d} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-4">
          <div className="bg-cream-soft border border-gold/15 rounded-sm p-5">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Signup funnel</p>
            <ol className="space-y-1.5 font-mono text-sm">
              {[
                { k: "applied", l: "Applied" },
                { k: "pending", l: "Pending review" },
                { k: "invited", l: "Invited (claimed)" },
                { k: "approved", l: "Approved" },
                { k: "declined", l: "Declined" },
                { k: "suspended", l: "Suspended" },
              ].map((s) => (
                <li key={s.k} className="flex items-baseline gap-3" data-testid={`funnel-${s.k}`}>
                  <span className="font-display font-semibold text-ink w-12 text-right">{a.funnel[s.k] ?? 0}</span>
                  <span className="text-muted-ink">{s.l}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="bg-cream-soft border border-gold/15 rounded-sm p-5">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Source breakdown</p>
            {a.source_breakdown.length === 0 ? (
              <p className="font-serif italic text-sm text-muted-ink">No data.</p>
            ) : (
              <ol className="space-y-1.5">
                {a.source_breakdown.map((s, i) => (
                  <li key={s.source} className="flex items-baseline gap-3 font-mono text-sm" data-testid={`source-${s.source}`}>
                    <span className="font-mono text-[10px] text-muted-ink w-5">{(i + 1).toString().padStart(2, "0")}</span>
                    <span className="font-display font-semibold text-ink flex-1 truncate">{s.source}</span>
                    <span className="text-gold font-semibold">{s.count}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </Section>

      {/* ─── ENGAGEMENT ──────────────────────────────────────────── */}
      <Section title="Engagement" subtitle="Who's active and what they're publishing" testid="analytics-engagement">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile testid="eng-active-7d" label="Active · 7d" value={e.active_7d} hint="Logged in" tone="ok" />
          <StatTile testid="eng-active-30d" label="Active · 30d" value={e.active_30d} />
          <StatTile testid="eng-essays-30d" label="Essays · 30d" value={e.essays_30d} hint={`${e.essays_total} lifetime`} />
          <StatTile testid="eng-replies-30d" label="Replies · 30d" value={e.replies_30d} hint={`${e.replies_total} lifetime`} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-4">
          <div className="bg-cream-soft border border-gold/15 rounded-sm p-5">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Content created · last 14 days</p>
            <BarChart
              rows={e.content_volume_14d}
              getValue={(row) => row.essays + row.posts}
              getLabel={(row) => row.day?.slice(5) || ""}
              color="bg-gold"
              testid="eng-content-chart"
            />
          </div>
          <div className="bg-cream-soft border border-gold/15 rounded-sm p-5">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Top contributors</p>
            {e.top_contributors.length === 0 ? (
              <p className="font-serif italic text-sm text-muted-ink">No essays yet.</p>
            ) : (
              <ol className="space-y-2">
                {e.top_contributors.map((c, i) => (
                  <li key={c.user_id} className="flex items-baseline gap-3" data-testid={`top-contrib-${c.user_id}`}>
                    <span className="font-mono text-[10px] text-muted-ink w-5">{(i + 1).toString().padStart(2, "0")}</span>
                    <span className="font-display font-semibold text-ink flex-1 truncate">{c.name}</span>
                    <span className="font-mono text-sm text-gold font-semibold">{c.essays}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </Section>

      {/* ─── RETENTION / CHURN ───────────────────────────────────── */}
      <Section title="Retention & churn" subtitle="Behavioural — based on last login" testid="analytics-retention">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile testid="ret-churn-rate" label="Churn rate" value={`${r.churn_rate_pct}%`} hint="Inactive 90+ days" tone={r.churn_rate_pct > 40 ? "warn" : "neutral"} />
          <StatTile testid="ret-atrisk-30-60" label="At risk · 30-60d" value={r.at_risk_30_60} hint="Lapsing" tone="warn" />
          <StatTile testid="ret-atrisk-60-90" label="At risk · 60-90d" value={r.at_risk_60_90} hint="Deep lapse" tone="warn" />
          <StatTile testid="ret-churned" label="Churned · 90d+" value={r.churned_90plus} hint={`Of ${r.ever_logged_in} ever-active`} tone="warn" />
        </div>
        <p className="font-serif italic text-xs text-muted-ink max-w-prose">
          Once a paid plan exists, churn will be redefined as cancellation. For now this is a behavioural proxy — useful for triggering re-engagement emails to lapsing members.
        </p>
      </Section>

      {/* ─── TRAFFIC ─────────────────────────────────────────────── */}
      <Section title="Traffic" subtitle="Pageviews via the in-app event tracker" testid="analytics-traffic">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile testid="tr-pv-7d" label="Pageviews · 7d" value={t.pageviews_7d} />
          <StatTile testid="tr-pv-30d" label="Pageviews · 30d" value={t.pageviews_30d} />
          <StatTile testid="tr-sessions-14d" label="Sessions · 14d" value={(t.daily_14d || []).reduce((a, b) => a + (b.unique_sessions || 0), 0)} />
          <StatTile testid="tr-users-14d" label="Members · 14d" value={(t.daily_14d || []).reduce((a, b) => a + (b.unique_users || 0), 0)} hint="Sum of daily unique (not deduped)" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-4">
          <div className="bg-cream-soft border border-gold/15 rounded-sm p-5">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Daily pageviews · last 14d</p>
            {t.daily_14d?.length === 0 ? (
              <p className="font-serif italic text-sm text-muted-ink py-6 text-center">No traffic data yet — analytics tracking just started.</p>
            ) : (
              <BarChart
                rows={t.daily_14d}
                getValue={(row) => row.pageviews}
                getLabel={(row) => row.day?.slice(5) || ""}
                color="bg-gold"
                testid="tr-daily-chart"
              />
            )}
          </div>
          <div className="bg-cream-soft border border-gold/15 rounded-sm p-5">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Top paths · 30d</p>
            {t.top_paths_30d.length === 0 ? (
              <p className="font-serif italic text-sm text-muted-ink">No data yet.</p>
            ) : (
              <ol className="space-y-1.5">
                {t.top_paths_30d.map((p, i) => (
                  <li key={p.path} className="flex items-baseline gap-3 font-mono text-sm" data-testid={`top-path-${i}`}>
                    <span className="text-[10px] text-muted-ink w-5">{(i + 1).toString().padStart(2, "0")}</span>
                    <span className="font-display font-semibold text-ink flex-1 truncate">{p.path}</span>
                    <span className="text-gold font-semibold">{p.views}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </Section>
    </div>
  );
}
