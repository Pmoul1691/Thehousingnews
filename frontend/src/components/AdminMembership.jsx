import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Admin Membership panel — list every user, search/filter them, click any
 * row to see a full profile + interaction stats + recent posts.
 *
 * Layout: searchable list (left) + detail pane (right). On mobile the list
 * stacks above the detail pane.
 */

const STATUS_OPTIONS = [
  { v: "", l: "All statuses" },
  { v: "approved", l: "Approved" },
  { v: "invited", l: "Invited" },
  { v: "pending", l: "Pending" },
  { v: "needs_application", l: "Needs app" },
  { v: "declined", l: "Declined" },
  { v: "suspended", l: "Suspended" },
];

function statusBadgeCls(status, suspended) {
  if (suspended) return "bg-deepred/10 text-deepred border border-deepred/40";
  if (status === "approved") return "bg-emerald-50 text-emerald-800 border border-emerald-200";
  if (status === "invited") return "bg-gold/10 text-gold border border-gold/40";
  if (status === "pending") return "bg-amber-50 text-amber-800 border border-amber-200";
  if (status === "declined") return "bg-slate-100 text-slate-600 border border-slate-300";
  return "bg-cream-soft text-muted-ink border border-gold/20";
}

function Avatar({ name, avatarPath, size = 36 }) {
  const [errored, setErrored] = useState(false);
  const letter = (name || "?").trim().charAt(0).toUpperCase() || "?";
  const dim = { width: size, height: size };
  if (avatarPath && !errored) {
    const apiBase = typeof window !== "undefined" ? window.location.origin : "";
    return (
      <img
        src={`${apiBase}/api/uploads/file/${avatarPath}`}
        alt={name}
        onError={() => setErrored(true)}
        className="rounded-full object-cover border border-gold/30 shrink-0"
        style={dim}
        loading="lazy"
      />
    );
  }
  return (
    <div
      className="rounded-full bg-cream-soft border border-gold/30 flex items-center justify-center shrink-0"
      style={dim}
    >
      <span className="font-display font-semibold text-gold" style={{ fontSize: Math.round(size * 0.4) }}>{letter}</span>
    </div>
  );
}

function StatPill({ label, value, testid }) {
  return (
    <div data-testid={testid} className="bg-white border border-gold/15 rounded-sm p-3">
      <div className="font-display font-semibold text-xl ink">{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted-ink mt-0.5">{label}</div>
    </div>
  );
}

function MemberRow({ m, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`member-row-${m.user_id}`}
      className={`w-full text-left flex items-center gap-3 px-3 py-2.5 border-b border-gold/10 transition-colors ${
        active ? "bg-gold/10 border-l-2 border-l-gold pl-[10px]" : "hover:bg-cream-soft"
      }`}
    >
      <Avatar name={m.name || m.email} avatarPath={m.avatar_path} size={32} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="font-display font-semibold text-[13px] ink truncate">{m.name || "—"}</span>
          {m.is_admin && <span className="font-mono text-[9px] uppercase text-gold shrink-0">admin</span>}
          {m.is_stub && <span className="font-mono text-[9px] uppercase text-muted-ink shrink-0">stub</span>}
        </div>
        <div className="font-mono text-[10px] text-muted-ink truncate">{m.email}</div>
      </div>
      <div className="flex flex-col items-end shrink-0">
        <span className={`font-mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm ${statusBadgeCls(m.status, m.suspended)}`}>
          {m.suspended ? "susp" : m.status?.slice(0, 6)}
        </span>
        <span className="font-mono text-[10px] text-muted-ink mt-1">{m.posts_total} posts</span>
      </div>
    </button>
  );
}

function MemberDetail({ userId, onMutated }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const r = await api.get(`/admin/dashboard/members/${userId}`);
      setData(r.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load user");
    } finally { setLoading(false); }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const toggleSuspend = async () => {
    if (!data) return;
    const path = data.user.suspended ? `/admin/users/${userId}/unsuspend` : `/admin/users/${userId}/suspend`;
    setBusy(true);
    try {
      await api.post(path);
      toast.success(data.user.suspended ? "Unsuspended" : "Suspended");
      await load();
      onMutated && onMutated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Action failed");
    } finally { setBusy(false); }
  };

  if (!userId) {
    return (
      <div className="bg-cream-soft border border-gold/15 rounded-sm p-10 text-center" data-testid="membership-empty-detail">
        <p className="font-serif italic text-muted-ink">Select a member to see their profile, stats, and posts.</p>
      </div>
    );
  }
  if (loading || !data) {
    return <p className="font-sans text-sm text-muted-ink py-12 text-center" data-testid="membership-detail-loading">Loading…</p>;
  }

  const { user, profile, stats, recent_posts } = data;
  const kindKeys = Object.keys(stats.posts_by_kind);
  const totalPosts = kindKeys.reduce((s, k) => s + stats.posts_by_kind[k].total, 0);

  return (
    <div className="bg-cream-soft border border-gold/15 rounded-sm" data-testid="membership-detail">
      {/* Header */}
      <div className="p-5 border-b border-gold/15 flex items-start gap-4">
        <Avatar name={user.name || user.email} avatarPath={profile.avatar_path} size={72} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-display font-semibold text-xl ink" data-testid="membership-detail-name">{user.name || "—"}</h3>
            <span className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm ${statusBadgeCls(user.status, user.suspended)}`}>
              {user.suspended ? "Suspended" : user.status}
            </span>
            {user.is_admin && <span className="font-mono text-[10px] uppercase text-gold border border-gold px-1.5 py-0.5 rounded-sm">admin</span>}
            {profile.is_stub && <span className="font-mono text-[10px] uppercase text-muted-ink border border-gold/30 px-1.5 py-0.5 rounded-sm">stub profile</span>}
          </div>
          <p className="font-sans text-sm text-muted-ink mt-1" data-testid="membership-detail-email">{user.email}</p>
          {profile.market && <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mt-1">{profile.market}</p>}
          {profile.bio && <p className="font-serif text-[14px] text-ink/80 mt-3 leading-relaxed">{profile.bio}</p>}
          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <Link to={`/profile/${user.user_id}`} target="_blank" rel="noopener noreferrer" data-testid="membership-view-profile" className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:underline">
              View public profile →
            </Link>
            {profile.linkedin_url && (
              <a href={profile.linkedin_url} target="_blank" rel="noopener noreferrer" className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:underline">
                LinkedIn →
              </a>
            )}
            <button
              type="button"
              onClick={toggleSuspend}
              disabled={busy}
              data-testid="membership-toggle-suspend"
              className={`font-sans text-xs uppercase tracking-wider font-semibold px-3 py-1 rounded-sm transition-colors disabled:opacity-50 ${
                user.suspended ? "bg-emerald-700 text-cream hover:bg-emerald-800" : "border border-deepred text-deepred hover:bg-deepred hover:text-cream"
              }`}
            >
              {user.suspended ? "Unsuspend" : "Suspend"}
            </button>
          </div>
        </div>
      </div>

      {/* Meta strip */}
      <div className="px-5 py-3 border-b border-gold/15 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 font-mono text-[11px] text-muted-ink" data-testid="membership-meta">
        <div><span className="text-gold uppercase tracking-wider">Joined</span><br/>{user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}</div>
        <div><span className="text-gold uppercase tracking-wider">Last login</span><br/>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}</div>
        <div><span className="text-gold uppercase tracking-wider">Source</span><br/>{user.source || "—"}</div>
        <div><span className="text-gold uppercase tracking-wider">ToS</span><br/>{user.tos_accepted_at ? new Date(user.tos_accepted_at).toLocaleDateString() : "—"}</div>
      </div>

      {/* Stats grid */}
      <div className="p-5">
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Interactions</p>
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2.5 mb-6">
          <StatPill label="Total posts" value={totalPosts} testid="stat-total-posts" />
          {kindKeys.map((k) => (
            <StatPill key={k} label={k} value={stats.posts_by_kind[k].total} testid={`stat-kind-${k}`} />
          ))}
          <StatPill label="Replies" value={stats.replies} testid="stat-replies" />
          <StatPill label="Reactions" value={stats.reactions} testid="stat-reactions" />
          <StatPill label="Briefs sent" value={stats.briefs_sent} testid="stat-briefs-sent" />
          <StatPill label="Briefs opened" value={stats.briefs_opened} testid="stat-briefs-opened" />
          <StatPill label="Briefs clicked" value={stats.briefs_clicked} testid="stat-briefs-clicked" />
          <StatPill label="Invites sent" value={stats.invites_sent} testid="stat-invites-sent" />
          <StatPill label="PATs live" value={stats.pats_live} testid="stat-pats-live" />
        </div>

        {/* Brief preferences */}
        <div className="flex items-center gap-4 flex-wrap mb-6 font-mono text-[11px] text-muted-ink" data-testid="membership-brief-prefs">
          <span className="uppercase tracking-wider text-gold">Brief prefs:</span>
          <span>Morning · {user.brief_morning_optout ? <span className="text-deepred">opted out</span> : "✓ on"}</span>
          <span>Evening · {user.brief_evening_optout ? <span className="text-deepred">opted out</span> : "✓ on"}</span>
        </div>

        {/* Recent posts */}
        <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-3">Recent posts</p>
        {recent_posts.length === 0 ? (
          <p className="font-serif italic text-sm text-muted-ink">No posts yet.</p>
        ) : (
          <ol className="space-y-2" data-testid="membership-recent-posts">
            {recent_posts.map((p) => {
              const href = p.kind === "essay" ? `/essays/${p.post_id}` : `/p/${p.post_id}`;
              const blurb = (p.title || p.text || "").trim();
              return (
                <li key={p.post_id} data-testid={`membership-post-${p.post_id}`} className="flex items-start gap-3 bg-white border border-gold/10 rounded-sm px-3 py-2">
                  <span className={`font-mono text-[9px] uppercase px-1.5 py-0.5 rounded-sm shrink-0 mt-0.5 ${
                    p.status === "approved" ? "bg-emerald-50 text-emerald-800" :
                    p.status === "pending_release" ? "bg-amber-50 text-amber-800" :
                    p.status === "flagged" ? "bg-deepred/10 text-deepred" : "bg-cream-soft text-muted-ink"
                  }`}>
                    {p.kind}·{p.status?.split("_")[0]}
                  </span>
                  <div className="flex-1 min-w-0">
                    <Link to={href} target="_blank" rel="noopener noreferrer" className="font-display font-semibold text-[13px] ink hover:text-gold line-clamp-2">
                      {blurb || "(empty)"}
                    </Link>
                    <p className="font-mono text-[10px] text-muted-ink mt-0.5">
                      {new Date(p.created_at).toLocaleString()}
                      {p.tags && p.tags.length > 0 && (
                        <span className="ml-2">
                          {p.tags.slice(0, 3).map((t) => <span key={t} className="text-gold/80 mr-1">#{t}</span>)}
                        </span>
                      )}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}

export default function AdminMembership() {
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(30);
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedUid, setSelectedUid] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit, offset };
      if (q) params.q = q;
      if (status) params.status = status;
      const r = await api.get("/admin/dashboard/members", { params });
      setMembers(r.data.items || []);
      setTotal(r.data.total || 0);
      if (!selectedUid && r.data.items?.length) {
        setSelectedUid(r.data.items[0].user_id);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load members");
    } finally { setLoading(false); }
  }, [q, status, limit, offset, selectedUid]);

  useEffect(() => { load(); }, [load]);

  const submitSearch = (e) => {
    e.preventDefault();
    setOffset(0);
    setQ(qInput.trim());
  };

  const hasNext = offset + limit < total;
  const hasPrev = offset > 0;

  return (
    <div className="space-y-6" data-testid="admin-membership">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">Membership</p>
          <h1 className="font-display font-semibold text-3xl ink mt-1 tracking-tight">All members.</h1>
          <p className="font-sans text-[12px] text-muted-ink mt-1">{total.toLocaleString()} total · click a row to view everything.</p>
        </div>
        <form onSubmit={submitSearch} className="flex items-center gap-2 flex-wrap" data-testid="membership-filters">
          <input
            type="search"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="Search name or email"
            data-testid="membership-search"
            className="border hairline bg-white rounded-sm px-3 py-2 font-sans text-sm focus:outline-none focus:border-gold min-w-[220px]"
          />
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); setOffset(0); }}
            data-testid="membership-status-select"
            className="border hairline bg-white rounded-sm px-3 py-2 font-sans text-sm focus:outline-none focus:border-gold"
          >
            {STATUS_OPTIONS.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
          </select>
          <button type="submit" data-testid="membership-search-submit" className="bg-ink text-cream font-sans font-semibold text-xs uppercase tracking-wider px-4 py-2 rounded-sm hover:bg-gold transition-colors">
            Filter
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-5">
        {/* List */}
        <div className="bg-cream-soft border border-gold/15 rounded-sm overflow-hidden" data-testid="membership-list">
          <div className="max-h-[640px] overflow-y-auto">
            {loading && members.length === 0 ? (
              <p className="font-sans text-sm text-muted-ink py-12 text-center">Loading…</p>
            ) : members.length === 0 ? (
              <p className="font-serif italic text-sm text-muted-ink py-12 text-center">No matches.</p>
            ) : members.map((m) => (
              <MemberRow
                key={m.user_id}
                m={m}
                active={selectedUid === m.user_id}
                onClick={() => setSelectedUid(m.user_id)}
              />
            ))}
          </div>
          <div className="px-3 py-2 border-t border-gold/15 flex items-center justify-between font-mono text-[11px] text-muted-ink">
            <button type="button" disabled={!hasPrev} onClick={() => setOffset(Math.max(0, offset - limit))} data-testid="membership-prev" className="font-sans uppercase tracking-wider disabled:opacity-40 hover:text-gold">← Prev</button>
            <span>{offset + 1}–{Math.min(offset + members.length, total)} / {total}</span>
            <button type="button" disabled={!hasNext} onClick={() => setOffset(offset + limit)} data-testid="membership-next" className="font-sans uppercase tracking-wider disabled:opacity-40 hover:text-gold">Next →</button>
          </div>
        </div>

        {/* Detail */}
        <MemberDetail userId={selectedUid} onMutated={load} />
      </div>
    </div>
  );
}
