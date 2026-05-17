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

export default function AdminAiModeration() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [decided, setDecided] = useState(false);
  const [kind, setKind] = useState("");
  const [busyId, setBusyId] = useState(null);

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
    </div>
  );
}
