import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago" }).format(new Date(iso));
  } catch { return ""; }
}

export default function AdminPromptsPanel() {
  const [prompts, setPrompts] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("active");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [p, s] = await Promise.all([
        api.get("/prompts"),
        api.get("/admin/prompts/suggestions").catch(() => ({ data: { items: [] } })),
      ]);
      setPrompts(p.data.items || []);
      setSuggestions(s.data.items || []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const create = async () => {
    if (title.trim().length < 3) { toast.error("Title is too short"); return; }
    setBusy(true);
    try {
      await api.post("/admin/prompts", { title: title.trim(), body: body.trim(), status });
      toast.success(status === "active" ? "Subject set live" : "Subject scheduled");
      setTitle(""); setBody("");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create");
    } finally { setBusy(false); }
  };

  const setActive = async (prompt_id) => {
    setBusy(true);
    try {
      const p = prompts.find((x) => x.prompt_id === prompt_id);
      await api.patch(`/admin/prompts/${prompt_id}`, { title: p.title, body: p.body || "", status: "active" });
      toast.success("Subject set active");
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const remove = async (prompt_id) => {
    if (!window.confirm("Delete this subject?")) return;
    try {
      await api.delete(`/admin/prompts/${prompt_id}`);
      toast.success("Deleted");
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const acceptSuggestion = async (s) => {
    setTitle(s.text);
    setBody(`Suggested by ${s.user_name}.`);
    try {
      await api.post(`/admin/prompts/suggestions/${s.suggestion_id}/accept`);
      toast.success("Suggestion loaded above. Edit and create.");
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const rejectSuggestion = async (s) => {
    try {
      await api.post(`/admin/prompts/suggestions/${s.suggestion_id}/reject`);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  if (loading) return <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>;

  return (
    <div className="space-y-12" data-testid="admin-prompts-panel">
      <section data-testid="admin-prompts-create" className="border hairline rounded-sm p-6 bg-cream">
        <p className="uppercase-label mb-3">New subject</p>
        <div className="space-y-3">
          <input
            data-testid="admin-prompts-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="A question or theme. One short line."
            maxLength={160}
            className="w-full bg-cream border hairline rounded-sm px-3 py-2 font-display font-semibold text-lg ink focus:outline-none focus:ring-1 focus:ring-gold"
          />
          <textarea
            data-testid="admin-prompts-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Optional. A paragraph of context."
            maxLength={2000}
            className="w-full bg-cream border hairline rounded-sm px-3 py-2 font-serif text-sm ink focus:outline-none focus:ring-1 focus:ring-gold min-h-[80px]"
          />
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1 border hairline rounded-sm p-0.5">
              {["active", "scheduled"].map((s) => (
                <button
                  key={s}
                  data-testid={`admin-prompts-status-${s}`}
                  type="button"
                  onClick={() => setStatus(s)}
                  className={`px-3 py-1 font-sans text-[11px] font-semibold uppercase tracking-wider transition-colors ${status === s ? "bg-gold text-cream" : "text-muted-ink hover:text-ink"}`}
                >
                  {s === "active" ? "Set live now" : "Queue for later"}
                </button>
              ))}
            </div>
            <button
              data-testid="admin-prompts-create-btn"
              onClick={create}
              disabled={busy || title.trim().length < 3}
              className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {busy ? "Saving..." : "Create"}
            </button>
          </div>
        </div>
      </section>

      <section data-testid="admin-prompts-list">
        <p className="uppercase-label mb-4">All subjects</p>
        {prompts.length === 0 ? (
          <p className="font-serif text-base text-muted-ink italic">None yet.</p>
        ) : (
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            {prompts.map((p) => (
              <div key={p.prompt_id} data-testid={`admin-prompt-${p.prompt_id}`} className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`font-sans text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-sm border ${p.status === "active" ? "text-gold border-gold" : "text-muted-ink border-[#E8D4A0]"}`}>
                      {p.status}
                    </span>
                    <span className="font-sans text-xs text-muted-ink">{formatDate(p.week_start)} – {formatDate(p.week_end)}</span>
                    <span className="font-sans text-xs text-muted-ink">. {p.response_count || 0} responses</span>
                  </div>
                  <div className="font-display font-semibold text-base ink">{p.title}</div>
                </div>
                <div className="flex items-center gap-3">
                  {p.status !== "active" && (
                    <button onClick={() => setActive(p.prompt_id)} data-testid={`admin-prompt-activate-${p.prompt_id}`} className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity">Set active</button>
                  )}
                  <button onClick={() => remove(p.prompt_id)} data-testid={`admin-prompt-delete-${p.prompt_id}`} className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors">Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section data-testid="admin-prompts-suggestions">
        <p className="uppercase-label mb-4">Member suggestions</p>
        {suggestions.length === 0 ? (
          <p className="font-serif text-base text-muted-ink italic">No open suggestions.</p>
        ) : (
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            {suggestions.map((s) => (
              <div key={s.suggestion_id} data-testid={`admin-suggestion-${s.suggestion_id}`} className="px-5 py-4">
                <div className="font-serif text-base ink mb-2">{s.text}</div>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="font-sans text-xs text-muted-ink">From {s.user_name} . {formatDate(s.created_at)}</div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => acceptSuggestion(s)} data-testid={`admin-suggestion-accept-${s.suggestion_id}`} className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity">Use as draft</button>
                    <button onClick={() => rejectSuggestion(s)} data-testid={`admin-suggestion-reject-${s.suggestion_id}`} className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors">Reject</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
