import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * AI Review queue — content Claude flagged or declined that needs an admin's
 * final call. "Approve override" restores the content; "Confirm decline"
 * permanently declines it.
 */

const CAT_LABELS = {
  fair_housing: "Fair Housing",
  antitrust: "Antitrust",
  confidentiality: "Confidentiality",
  mls_violation: "MLS",
  respa: "RESPA",
  unlicensed_advice: "Unlicensed advice",
  spam: "Spam",
  harassment: "Harassment",
  misrepresentation: "Misrepresentation",
  off_topic: "Off-topic",
  political: "Political",
  defamation: "Defamation",
  unverified_rumor: "Rumor",
  borderline_promotion: "Self-promo",
  none: "Clean",
};

function StatTile({ label, value, hint, testid, tone = "neutral" }) {
  const toneClass = {
    neutral: "border-gold/15",
    warn: "border-deepred/40",
    ok: "border-emerald-700/30",
  }[tone];
  return (
    <div data-testid={testid} className={`bg-cream-soft border ${toneClass} rounded-sm p-4`}>
      <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink">{label}</p>
      <p className="font-display font-semibold text-3xl ink mt-1.5">{value}</p>
      {hint ? <p className="font-serif italic text-xs text-muted-ink mt-1">{hint}</p> : null}
    </div>
  );
}

function VerdictBadge({ verdict, score }) {
  const cls = verdict === "decline"
    ? "bg-deepred text-cream"
    : "bg-gold/20 text-gold border border-gold/40";
  return (
    <span data-testid={`verdict-${verdict}`} className={`inline-flex items-center gap-1.5 font-sans text-[10px] uppercase tracking-wider font-semibold px-2 py-1 rounded-sm ${cls}`}>
      {verdict === "decline" ? "Decline" : "Flag"}
      <span className="font-mono opacity-80">· {score ?? "?"}</span>
    </span>
  );
}

function CategoryChips({ cats }) {
  const list = (cats || []).filter((c) => c && c !== "none");
  if (list.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {list.map((c) => (
        <span key={c} className="font-mono text-[10px] bg-white border border-gold/20 rounded-sm px-1.5 py-0.5 text-ink/80">
          {CAT_LABELS[c] || c}
        </span>
      ))}
    </div>
  );
}

function ReviewCard({ r, onDecide, busyId }) {
  const isBusy = busyId === r.id;
  const author = r.author || {};
  const targetPath = r.target_kind === "reply"
    ? (r.target?.post_id ? `/posts/${r.target.post_id}#reply-${r.target_id}` : null)
    : `/essays/${r.target_id}`;
  const targetTitle = r.target?.title || r.title || (r.target_kind === "reply" ? "Reply" : "Untitled");

  return (
    <article data-testid={`mod-review-${r.id}`} className="bg-cream border border-gold/15 rounded-sm p-5">
      <header className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <VerdictBadge verdict={r.verdict} score={r.risk_score} />
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-ink">
              {r.target_kind}
            </span>
            {r.target?.kind === "essay" ? (
              <span className="font-mono text-[10px] uppercase tracking-wider text-gold">Essay</span>
            ) : null}
          </div>
          <h3 className="font-display font-semibold text-lg ink mt-2 leading-snug">
            {targetPath ? (
              <Link to={targetPath} className="hover:text-gold" target="_blank" rel="noopener noreferrer">{targetTitle}</Link>
            ) : targetTitle}
          </h3>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink mt-1">
            {author.name || "(unknown)"} {author.email ? `· ${author.email}` : ""}
            {r.reviewed_at ? ` · reviewed ${new Date(r.reviewed_at).toLocaleString()}` : ""}
          </p>
          <CategoryChips cats={r.categories} />
        </div>
      </header>

      <blockquote className="font-serif italic text-sm text-ink/80 border-l-2 border-gold/30 pl-4 my-3 line-clamp-5">
        {r.content_excerpt || "(no content)"}
      </blockquote>

      {r.reasoning ? (
        <div className="bg-white/60 border border-gold/15 rounded-sm p-3 mt-3">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-1">Claude&apos;s reasoning</p>
          <p className="font-serif text-sm ink/90 leading-relaxed">{r.reasoning}</p>
          {r.quoted_excerpts?.length > 0 ? (
            <p className="font-mono text-[11px] text-muted-ink mt-2">
              Triggers: {r.quoted_excerpts.map((q, i) => (
                <span key={i} className="inline-block bg-deepred/10 text-deepred px-1.5 py-0.5 rounded-sm mr-1 mb-1">
                  &ldquo;{q}&rdquo;
                </span>
              ))}
            </p>
          ) : null}
        </div>
      ) : null}

      {r.admin_decision ? (
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted-ink mt-4" data-testid={`mod-decided-${r.id}`}>
          Decided · {r.admin_decision.replace("_", " ")}
          {r.admin_decided_at ? ` · ${new Date(r.admin_decided_at).toLocaleString()}` : ""}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2 mt-4">
          <button
            type="button"
            disabled={isBusy}
            onClick={() => onDecide(r.id, "approve_override")}
            data-testid={`mod-approve-${r.id}`}
            className="font-sans text-[11px] uppercase tracking-wider font-semibold bg-emerald-700 text-cream px-3 py-1.5 rounded-sm hover:bg-emerald-800 disabled:opacity-40"
          >
            {isBusy ? "…" : "Override · Approve"}
          </button>
          <button
            type="button"
            disabled={isBusy}
            onClick={() => onDecide(r.id, "confirm_decline")}
            data-testid={`mod-decline-${r.id}`}
            className="font-sans text-[11px] uppercase tracking-wider font-semibold border border-deepred text-deepred hover:bg-deepred hover:text-cream px-3 py-1.5 rounded-sm disabled:opacity-40"
          >
            {isBusy ? "…" : "Confirm decline"}
          </button>
        </div>
      )}
    </article>
  );
}

function PatternsPanel({ data, loading, days, onDaysChange }) {
  if (loading) {
    return <p className="font-serif italic text-sm text-muted-ink py-10 text-center">Loading patterns.</p>;
  }
  if (!data) return null;
  const acc = data.claude_accuracy || {};
  const maxDaily = Math.max(1, ...(data.daily_volume || []).map((d) => d.reviewed));

  return (
    <div className="space-y-6" data-testid="mod-patterns">
      <div className="flex items-center justify-between flex-wrap gap-2 border-b border-gold/15 pb-2">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink">Window</p>
        <div className="flex items-center gap-1">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => onDaysChange(d)}
              data-testid={`mod-patterns-window-${d}`}
              className={`font-sans text-[11px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-sm ${days === d ? "bg-gold text-cream" : "text-muted-ink hover:text-ink"}`}
            >{d}d</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <section className="bg-cream-soft border border-gold/15 rounded-sm p-5">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Top violation categories</p>
          {(data.top_categories || []).length === 0 ? (
            <p className="font-serif italic text-sm text-muted-ink">No violations in this window.</p>
          ) : (
            <ol className="space-y-2">
              {data.top_categories.map((c, i) => (
                <li key={c.category} data-testid={`mod-cat-${c.category}`} className="flex items-baseline gap-3">
                  <span className="font-mono text-[10px] text-muted-ink w-5">{(i + 1).toString().padStart(2, "0")}</span>
                  <span className="font-display font-semibold text-base ink flex-1">{CAT_LABELS[c.category] || c.category}</span>
                  <span className="font-mono text-sm text-gold font-semibold">{c.count}</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="bg-cream-soft border border-gold/15 rounded-sm p-5">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Members generating the most flags</p>
          {(data.top_flagged_users || []).length === 0 ? (
            <p className="font-serif italic text-sm text-muted-ink">No member has triggered a flag in this window.</p>
          ) : (
            <ol className="space-y-2.5">
              {data.top_flagged_users.map((u, i) => (
                <li key={u.user_id || i} data-testid={`mod-user-${u.user_id}`} className="flex items-baseline gap-3 border-b border-gold/10 last:border-0 pb-2 last:pb-0">
                  <span className="font-mono text-[10px] text-muted-ink w-5">{(i + 1).toString().padStart(2, "0")}</span>
                  <div className="flex-1 min-w-0">
                    <p className="font-display font-semibold text-sm ink truncate">{u.name}</p>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-muted-ink truncate">{u.email}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm text-deepred font-semibold">{u.declines}d · {u.flags}f</p>
                    <p className="font-mono text-[10px] text-muted-ink">{u.total} total</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="bg-cream-soft border border-gold/15 rounded-sm p-5 lg:col-span-2">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Daily volume · last 14 days</p>
          {(data.daily_volume || []).length === 0 ? (
            <p className="font-serif italic text-sm text-muted-ink">No moderation activity yet.</p>
          ) : (
            <div className="flex items-end gap-2 h-32" data-testid="mod-daily-chart">
              {data.daily_volume.map((d) => {
                const pct = Math.round(100 * d.reviewed / maxDaily);
                const flaggedPct = d.reviewed ? Math.round(100 * d.flagged / d.reviewed) : 0;
                const declinedPct = d.reviewed ? Math.round(100 * d.declined / d.reviewed) : 0;
                return (
                  <div key={d.day} className="flex-1 flex flex-col items-center" title={`${d.day}: ${d.reviewed} reviewed, ${d.flagged} flagged, ${d.declined} declined`}>
                    <div className="w-full h-full flex flex-col justify-end relative">
                      <div className="w-full bg-gold/30 rounded-t-sm" style={{ height: `${pct}%` }}>
                        <div className="bg-gold w-full" style={{ height: `${flaggedPct}%` }} />
                        <div className="bg-deepred w-full" style={{ height: `${declinedPct}%` }} />
                      </div>
                    </div>
                    <span className="font-mono text-[8px] text-muted-ink mt-1">{d.day.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          )}
          <div className="flex items-center gap-4 mt-3 font-mono text-[10px] text-muted-ink">
            <span><span className="inline-block w-2 h-2 bg-gold/30 mr-1"/>Approved</span>
            <span><span className="inline-block w-2 h-2 bg-gold mr-1"/>Flagged</span>
            <span><span className="inline-block w-2 h-2 bg-deepred mr-1"/>Declined</span>
          </div>
        </section>

        <section className="bg-ink text-cream rounded-sm p-5 lg:col-span-2" data-testid="mod-accuracy">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Claude / admin agreement · {days}d</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
            <div>
              <p className="font-display font-semibold text-3xl text-cream">{acc.agreement_pct ?? "—"}{acc.agreement_pct != null ? "%" : ""}</p>
              <p className="font-mono text-[10px] uppercase tracking-wider text-cream/70 mt-1">Admin agreed with Claude</p>
            </div>
            <div>
              <p className="font-display font-semibold text-3xl text-cream">{acc.decided_total ?? 0}</p>
              <p className="font-mono text-[10px] uppercase tracking-wider text-cream/70 mt-1">Decisions logged</p>
            </div>
            <div>
              <p className="font-display font-semibold text-3xl text-emerald-300">{acc.admin_overrode ?? 0}</p>
              <p className="font-mono text-[10px] uppercase tracking-wider text-cream/70 mt-1">Overrode → approved</p>
            </div>
            <div>
              <p className="font-display font-semibold text-3xl text-deepred">{acc.admin_agreed ?? 0}</p>
              <p className="font-mono text-[10px] uppercase tracking-wider text-cream/70 mt-1">Confirmed decline</p>
            </div>
          </div>
          <p className="font-serif italic text-xs text-cream/60 mt-3">
            Use the override rate to retune the prompt. A high override rate means Claude is too aggressive; a low rate with rising user reports means it&apos;s too lenient.
          </p>
        </section>
      </div>
    </div>
  );
}

export default function AdminAiModeration() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [decided, setDecided] = useState(false);
  const [kind, setKind] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [view, setView] = useState("queue"); // "queue" | "patterns"
  const [patterns, setPatterns] = useState(null);
  const [patternsLoading, setPatternsLoading] = useState(false);
  const [patternsDays, setPatternsDays] = useState(30);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [q, s] = await Promise.all([
        api.get("/admin/moderation/queue", { params: { decided, kind: kind || undefined, limit: 100 } }),
        api.get("/admin/moderation/stats"),
      ]);
      setItems(q.data.items || []);
      setStats(s.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load moderation queue");
    } finally { setLoading(false); }
  }, [decided, kind]);

  useEffect(() => { load(); }, [load]);

  const loadPatterns = useCallback(async () => {
    setPatternsLoading(true);
    try {
      const r = await api.get("/admin/moderation/patterns", { params: { days: patternsDays } });
      setPatterns(r.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load patterns");
    } finally { setPatternsLoading(false); }
  }, [patternsDays]);

  useEffect(() => {
    if (view === "patterns") loadPatterns();
  }, [view, loadPatterns]);

  const decide = async (reviewId, decision) => {
    if (!window.confirm(decision === "approve_override"
      ? "Override Claude and publish this content?"
      : "Confirm decline — content stays hidden permanently?")) return;
    setBusyId(reviewId);
    try {
      await api.post(`/admin/moderation/${reviewId}/decide`, { decision });
      toast.success(decision === "approve_override" ? "Override approved" : "Decline confirmed");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Decision failed");
    } finally { setBusyId(null); }
  };

  return (
    <div className="space-y-6" data-testid="admin-aimoderation">
      <div className="flex items-center gap-4 border-b border-gold/15">
        {[
          { k: "queue", l: "Queue" },
          { k: "patterns", l: "Patterns" },
        ].map((t) => (
          <button
            key={t.k}
            type="button"
            onClick={() => setView(t.k)}
            data-testid={`mod-view-${t.k}`}
            className={`pb-2.5 font-display font-semibold text-sm transition-colors ${view === t.k ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
          >
            {t.l}
          </button>
        ))}
      </div>

      {view === "patterns" ? (
        <PatternsPanel data={patterns} loading={patternsLoading} days={patternsDays} onDaysChange={setPatternsDays} />
      ) : (
      <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile testid="mod-stat-pending" label="Pending" value={stats?.pending ?? "—"} hint="Awaiting your call" tone={stats?.pending > 0 ? "warn" : "ok"} />
        <StatTile testid="mod-stat-flagged" label="Flagged · 24h" value={stats?.flagged_24h ?? "—"} hint="Borderline" />
        <StatTile testid="mod-stat-declined" label="Declined · 24h" value={stats?.declined_24h ?? "—"} hint="Clear violations" tone="warn" />
        <StatTile testid="mod-stat-reviewed" label="Reviewed · 24h" value={stats?.reviewed_24h ?? "—"} hint="Total processed" />
      </div>

      <div className="flex flex-wrap items-center gap-3 border-b border-gold/15 pb-3">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          data-testid="mod-filter-kind"
          className="bg-cream border hairline rounded-sm px-2.5 py-1.5 font-sans text-xs ink focus:outline-none focus:ring-1 focus:ring-gold"
        >
          <option value="">All kinds</option>
          <option value="essay">Essays</option>
          <option value="post">Posts</option>
          <option value="reply">Replies</option>
        </select>
        <label className="flex items-center gap-1.5 font-sans text-xs text-muted-ink cursor-pointer">
          <input
            type="checkbox"
            checked={decided}
            onChange={(e) => setDecided(e.target.checked)}
            data-testid="mod-filter-decided"
            className="accent-gold cursor-pointer"
          />
          Include decided
        </label>
        <button
          type="button"
          onClick={load}
          data-testid="mod-refresh"
          className="ml-auto font-sans text-[11px] uppercase tracking-wider font-semibold text-gold hover:underline"
        >
          Refresh
        </button>
      </div>

      {loading && items.length === 0 ? (
        <p className="font-serif italic text-sm text-muted-ink py-12 text-center">Loading reviews.</p>
      ) : items.length === 0 ? (
        <div className="bg-cream-soft border border-gold/15 rounded-sm py-16 text-center" data-testid="mod-empty">
          <p className="font-display font-semibold text-xl ink">Nothing to review.</p>
          <p className="font-serif italic text-sm text-muted-ink mt-1">
            {decided ? "No decided items match the current filter." : "Claude has cleared every recent submission."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((r) => (
            <ReviewCard key={r.id} r={r} onDecide={decide} busyId={busyId} />
          ))}
        </div>
      )}
      </>
      )}
    </div>
  );
}
