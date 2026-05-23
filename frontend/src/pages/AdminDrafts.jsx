import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const STATUS_COLORS = {
  draft: { bg: "#FBF6E8", text: "#AD893E", border: "#E8D4A0" },
  queued: { bg: "#EAF4FF", text: "#1F60AB", border: "#BFD7F2" },
  sending: { bg: "#EAF4FF", text: "#1F60AB", border: "#BFD7F2" },
  sent: { bg: "#E8F1E8", text: "#3C6B3E", border: "#BFDDC0" },
  cancelled: { bg: "#F4E5E5", text: "#7A3232", border: "#E2BFBF" },
};

function StatusBadge({ status }) {
  const k = (status || "draft").toLowerCase();
  const c = STATUS_COLORS[k] || STATUS_COLORS.draft;
  return (
    <span
      data-testid={`broadcast-status-${k}`}
      className="font-sans text-[10px] uppercase tracking-widest font-semibold px-2 py-0.5 rounded-sm border"
      style={{ background: c.bg, color: c.text, borderColor: c.border }}
    >
      {k}
    </span>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const DEFAULT_HTML = `<div style="font-family:Georgia,serif; color:#2C2410; background:#FDFAF4; padding:24px;">
  <p>Hello,</p>
  <p>Write your newsletter here. You can paste raw HTML, or write plain text with line breaks.</p>
  <p>The Editors</p>
</div>`;

function DraftDrawer({ open, mode, initial, defaults, audiences, onClose, onSaved }) {
  // `mode` is "create" or "edit"
  const [subject, setSubject] = useState("");
  const [html, setHtml] = useState(DEFAULT_HTML);
  const [audienceId, setAudienceId] = useState("");
  const [fromName, setFromName] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && initial) {
      setSubject(initial.subject || "");
      setHtml(initial.html || DEFAULT_HTML);
      setAudienceId(initial.audience_id || defaults?.default_audience_id || "");
      // Resend returns `from` as "Name <email>" — parse out for the form.
      const from = initial.from || "";
      const m = from.match(/^(.*?)\s*<(.+)>$/);
      setFromName(m ? m[1].trim() : (defaults?.from_name || ""));
      setFromEmail(m ? m[2].trim() : (from || defaults?.from_email || ""));
      setName(initial.name || "");
    } else {
      setSubject("");
      setHtml(DEFAULT_HTML);
      setAudienceId(defaults?.default_audience_id || "");
      setFromName(defaults?.from_name || "");
      setFromEmail(defaults?.from_email || "");
      setName("");
    }
    setPreview(false);
  }, [open, mode, initial, defaults]);

  if (!open) return null;

  const save = async () => {
    if (!subject.trim() || !html.trim() || !audienceId) {
      toast.error("Subject, body, and audience are all required.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        audience_id: audienceId,
        subject,
        html,
        from_email: fromEmail || undefined,
        from_name: fromName || undefined,
        name: name || undefined,
      };
      if (mode === "edit" && initial?.id) {
        await api.patch(`/admin/broadcasts/${initial.id}`, body);
        toast.success("Draft updated.");
      } else {
        await api.post("/admin/broadcasts", body);
        toast.success("Draft created.");
      }
      onSaved?.();
      onClose?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex" data-testid="draft-drawer">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="flex-1 bg-black/40 backdrop-blur-sm"
        data-testid="draft-drawer-backdrop"
      />
      <div className="w-full max-w-2xl bg-cream border-l border-gold-light shadow-xl overflow-y-auto">
        <div className="p-6 border-b border-gold-light flex items-center justify-between">
          <h2 className="font-sans text-xl font-semibold text-ink">
            {mode === "edit" ? "Edit draft" : "New draft"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            data-testid="draft-drawer-close"
            className="text-ink/60 hover:text-ink text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div>
            <label className="block font-sans text-[11px] uppercase tracking-widest font-semibold text-gold mb-1.5">
              Subject
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              data-testid="draft-subject-input"
              placeholder="e.g. Housing News · Morning Brief · Mon Feb 24"
              className="w-full font-sans text-sm border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold"
            />
          </div>

          <div>
            <label className="block font-sans text-[11px] uppercase tracking-widest font-semibold text-gold mb-1.5">
              Audience
            </label>
            <select
              value={audienceId}
              onChange={(e) => setAudienceId(e.target.value)}
              data-testid="draft-audience-select"
              className="w-full font-sans text-sm border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold"
            >
              <option value="">— Pick an audience —</option>
              {audiences.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.id.slice(0, 8)}…)
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-sans text-[11px] uppercase tracking-widest font-semibold text-gold mb-1.5">
                From name
              </label>
              <input
                type="text"
                value={fromName}
                onChange={(e) => setFromName(e.target.value)}
                data-testid="draft-from-name-input"
                className="w-full font-sans text-sm border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold"
              />
            </div>
            <div>
              <label className="block font-sans text-[11px] uppercase tracking-widest font-semibold text-gold mb-1.5">
                From email
              </label>
              <input
                type="email"
                value={fromEmail}
                onChange={(e) => setFromEmail(e.target.value)}
                data-testid="draft-from-email-input"
                className="w-full font-sans text-sm border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold"
              />
            </div>
          </div>

          <div>
            <label className="block font-sans text-[11px] uppercase tracking-widest font-semibold text-gold mb-1.5">
              Internal name (optional — for your dashboard only)
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="draft-internal-name-input"
              placeholder="e.g. Morning brief / 2026-02-24"
              className="w-full font-sans text-sm border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="font-sans text-[11px] uppercase tracking-widest font-semibold text-gold">
                Body (HTML)
              </label>
              <button
                type="button"
                onClick={() => setPreview((p) => !p)}
                data-testid="draft-preview-toggle"
                className="font-sans text-[11px] uppercase tracking-widest font-semibold text-gold hover:text-ink"
              >
                {preview ? "Edit HTML" : "Preview"}
              </button>
            </div>
            {preview ? (
              <div
                data-testid="draft-html-preview"
                className="border border-gold-light bg-white rounded-sm p-4 min-h-[400px]"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            ) : (
              <textarea
                value={html}
                onChange={(e) => setHtml(e.target.value)}
                data-testid="draft-html-input"
                spellCheck={false}
                className="w-full font-mono text-xs border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold min-h-[400px]"
              />
            )}
          </div>
        </div>

        <div className="p-6 border-t border-gold-light flex items-center justify-end gap-3 sticky bottom-0 bg-cream">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            data-testid="draft-cancel-btn"
            className="font-sans text-xs uppercase tracking-widest font-semibold text-ink/60 px-4 py-2 hover:text-ink disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={busy}
            data-testid="draft-save-btn"
            className="font-sans text-xs uppercase tracking-widest font-semibold bg-ink text-cream px-5 py-2 rounded-sm hover:bg-gold disabled:opacity-50"
          >
            {busy ? "Saving…" : mode === "edit" ? "Save changes" : "Save draft"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SendDialog({ broadcast, onClose, onSent }) {
  // null when closed; broadcast object when open. Supports "send now" and "schedule".
  const [mode, setMode] = useState("now");
  const [whenLocal, setWhenLocal] = useState("");
  const [busy, setBusy] = useState(false);

  if (!broadcast) return null;

  const fire = async () => {
    setBusy(true);
    try {
      let scheduled_at = null;
      if (mode === "schedule") {
        if (!whenLocal) {
          toast.error("Pick a date and time first.");
          setBusy(false);
          return;
        }
        // Convert local datetime-local input to ISO-8601 UTC string.
        scheduled_at = new Date(whenLocal).toISOString();
      }
      await api.post(`/admin/broadcasts/${broadcast.id}/send`, { scheduled_at });
      toast.success(scheduled_at ? "Broadcast scheduled." : "Broadcast queued for send.");
      onSent?.();
      onClose?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-6" data-testid="send-dialog">
      <div className="bg-cream border border-gold-light rounded-sm w-full max-w-md p-6 shadow-xl">
        <h3 className="font-sans text-lg font-semibold text-ink mb-2">Send broadcast</h3>
        <p className="font-serif text-sm text-ink/80 mb-4">
          <span className="font-semibold">{broadcast.subject || "(no subject)"}</span>
          <br />
          <span className="text-ink/60">This will send to the broadcast's full audience. There's no undo.</span>
        </p>

        <div className="space-y-3 mb-5">
          <label className="flex items-center gap-2 cursor-pointer" data-testid="send-mode-now">
            <input
              type="radio"
              name="send-mode"
              checked={mode === "now"}
              onChange={() => setMode("now")}
              className="accent-gold"
            />
            <span className="font-sans text-sm text-ink">Send immediately</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer" data-testid="send-mode-schedule">
            <input
              type="radio"
              name="send-mode"
              checked={mode === "schedule"}
              onChange={() => setMode("schedule")}
              className="accent-gold"
            />
            <span className="font-sans text-sm text-ink">Schedule for later</span>
          </label>
          {mode === "schedule" && (
            <input
              type="datetime-local"
              value={whenLocal}
              onChange={(e) => setWhenLocal(e.target.value)}
              data-testid="send-schedule-when"
              className="w-full font-sans text-sm border border-gold-light bg-white px-3 py-2 rounded-sm focus:outline-none focus:border-gold ml-6"
            />
          )}
        </div>

        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            data-testid="send-dialog-cancel"
            className="font-sans text-xs uppercase tracking-widest font-semibold text-ink/60 px-4 py-2 hover:text-ink disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={fire}
            disabled={busy}
            data-testid="send-dialog-confirm"
            className="font-sans text-xs uppercase tracking-widest font-semibold bg-gold text-cream px-5 py-2 rounded-sm hover:bg-ink disabled:opacity-50"
          >
            {busy ? "Sending…" : mode === "now" ? "Send now" : "Schedule"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminDrafts() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [broadcasts, setBroadcasts] = useState([]);
  const [audiences, setAudiences] = useState([]);
  const [audienceById, setAudienceById] = useState({});
  const [defaults, setDefaults] = useState(null);
  const [filter, setFilter] = useState("all");
  const [fetching, setFetching] = useState(true);
  const [drawer, setDrawer] = useState({ open: false, mode: "create", initial: null });
  const [sendTarget, setSendTarget] = useState(null);

  useEffect(() => {
    if (!loading && (!user || !user.is_admin)) {
      navigate("/");
    }
  }, [loading, user, navigate]);

  const load = useCallback(async () => {
    setFetching(true);
    try {
      const [b, a, d] = await Promise.all([
        api.get("/admin/broadcasts"),
        api.get("/admin/broadcasts/audiences"),
        api.get("/admin/broadcasts/defaults"),
      ]);
      setBroadcasts(b.data?.data || []);
      setAudiences(a.data?.data || []);
      const map = {};
      (a.data?.data || []).forEach((x) => { map[x.id] = x; });
      setAudienceById(map);
      setDefaults(d.data || null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load broadcasts");
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (filter === "all") return broadcasts;
    return broadcasts.filter((b) => (b.status || "").toLowerCase() === filter);
  }, [broadcasts, filter]);

  const counts = useMemo(() => {
    const c = { all: broadcasts.length, draft: 0, queued: 0, sent: 0 };
    broadcasts.forEach((b) => {
      const s = (b.status || "").toLowerCase();
      if (s === "draft") c.draft += 1;
      else if (s === "sent") c.sent += 1;
      else if (s === "queued" || s === "sending") c.queued += 1;
    });
    return c;
  }, [broadcasts]);

  const openCreate = () => {
    setDrawer({ open: true, mode: "create", initial: null });
  };

  const openEdit = async (b) => {
    try {
      const r = await api.get(`/admin/broadcasts/${b.id}`);
      setDrawer({ open: true, mode: "edit", initial: r.data });
    } catch (e) {
      toast.error("Failed to load broadcast");
    }
  };

  const handleDelete = async (b) => {
    if (!window.confirm(`Delete draft "${b.subject || "(untitled)"}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/admin/broadcasts/${b.id}`);
      toast.success("Draft deleted.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  if (loading || !user || !user.is_admin) {
    return (
      <div className="max-w-5xl mx-auto p-8">
        <p className="font-serif text-ink/60">Loading…</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 lg:p-8" data-testid="admin-drafts-page">
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <Link to="/admin" className="font-sans text-xs uppercase tracking-widest font-semibold text-gold hover:text-ink">
            ← Admin
          </Link>
          <h1 className="font-sans text-3xl font-semibold text-ink mt-2">Broadcasts</h1>
          <p className="font-serif text-sm text-ink/70 mt-1">
            Draft, schedule, and send newsletters via Resend.
          </p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          data-testid="new-draft-btn"
          className="font-sans text-xs uppercase tracking-widest font-semibold bg-ink text-cream px-5 py-2.5 rounded-sm hover:bg-gold"
        >
          + New draft
        </button>
      </div>

      <div className="flex items-center gap-2 mt-6 mb-4 border-b border-gold-light pb-2">
        {[
          ["all", `All (${counts.all})`],
          ["draft", `Drafts (${counts.draft})`],
          ["queued", `Scheduled (${counts.queued})`],
          ["sent", `Sent (${counts.sent})`],
        ].map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setFilter(k)}
            data-testid={`filter-${k}`}
            className={`font-sans text-[11px] uppercase tracking-widest font-semibold px-3 py-1.5 rounded-sm transition-colors ${
              filter === k
                ? "bg-ink text-cream"
                : "text-ink/60 hover:text-ink hover:bg-gold-light/50"
            }`}
          >
            {label}
          </button>
        ))}
        <div className="ml-auto">
          <button
            type="button"
            onClick={load}
            disabled={fetching}
            data-testid="refresh-btn"
            className="font-sans text-[11px] uppercase tracking-widest font-semibold text-gold hover:text-ink disabled:opacity-50"
          >
            {fetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {filtered.length === 0 && !fetching ? (
        <div className="bg-cream-light border border-gold-light rounded-sm p-10 text-center">
          <p className="font-serif text-ink/70">
            {filter === "all"
              ? "No broadcasts yet. Hit “New draft” to compose your first."
              : `No ${filter} broadcasts.`}
          </p>
        </div>
      ) : (
        <div className="bg-cream-light border border-gold-light rounded-sm overflow-hidden">
          <table className="w-full" data-testid="broadcasts-table">
            <thead>
              <tr className="border-b border-gold-light">
                <th className="text-left font-sans text-[10px] uppercase tracking-widest font-semibold text-gold px-4 py-3">Subject</th>
                <th className="text-left font-sans text-[10px] uppercase tracking-widest font-semibold text-gold px-4 py-3">Status</th>
                <th className="text-left font-sans text-[10px] uppercase tracking-widest font-semibold text-gold px-4 py-3">Audience</th>
                <th className="text-left font-sans text-[10px] uppercase tracking-widest font-semibold text-gold px-4 py-3">Created</th>
                <th className="text-left font-sans text-[10px] uppercase tracking-widest font-semibold text-gold px-4 py-3">Sent</th>
                <th className="text-right font-sans text-[10px] uppercase tracking-widest font-semibold text-gold px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((b) => {
                const isDraft = (b.status || "").toLowerCase() === "draft";
                const aud = audienceById[b.audience_id];
                return (
                  <tr key={b.id} className="border-b border-gold-light/50 hover:bg-cream" data-testid={`row-${b.id}`}>
                    <td className="px-4 py-3 max-w-md">
                      <div className="font-sans text-sm font-semibold text-ink truncate" title={b.subject}>
                        {b.subject || "(no subject)"}
                      </div>
                      {b.name && (
                        <div className="font-serif text-xs text-ink/50 truncate" title={b.name}>{b.name}</div>
                      )}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={b.status} /></td>
                    <td className="px-4 py-3 font-serif text-sm text-ink/80">
                      {aud?.name || (b.audience_id || "").slice(0, 8) + "…"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-ink/60">{fmtDate(b.created_at)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink/60">
                      {b.sent_at ? fmtDate(b.sent_at) : (b.scheduled_at ? `⏱ ${fmtDate(b.scheduled_at)}` : "—")}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {isDraft ? (
                        <>
                          <button
                            type="button"
                            onClick={() => openEdit(b)}
                            data-testid={`edit-${b.id}`}
                            className="font-sans text-[11px] uppercase tracking-widest font-semibold text-gold hover:text-ink mr-3"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setSendTarget(b)}
                            data-testid={`send-${b.id}`}
                            className="font-sans text-[11px] uppercase tracking-widest font-semibold text-cream bg-ink hover:bg-gold px-3 py-1 rounded-sm mr-3"
                          >
                            Send / Schedule
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(b)}
                            data-testid={`delete-${b.id}`}
                            className="font-sans text-[11px] uppercase tracking-widest font-semibold text-ink/40 hover:text-red-700"
                          >
                            Delete
                          </button>
                        </>
                      ) : (
                        <span className="font-serif text-xs text-ink/40">
                          {b.status === "sent" ? "Locked" : "In progress"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <DraftDrawer
        open={drawer.open}
        mode={drawer.mode}
        initial={drawer.initial}
        defaults={defaults}
        audiences={audiences}
        onClose={() => setDrawer({ open: false, mode: "create", initial: null })}
        onSaved={load}
      />
      <SendDialog
        broadcast={sendTarget}
        onClose={() => setSendTarget(null)}
        onSent={load}
      />
    </div>
  );
}
