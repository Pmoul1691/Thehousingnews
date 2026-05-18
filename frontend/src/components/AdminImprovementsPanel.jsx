import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const STATUSES = ["new", "reviewing", "done", "dismissed"];

export default function AdminImprovementsPanel() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [status, setStatus] = useState("new");
  const [loading, setLoading] = useState(false);
  const [actingId, setActingId] = useState(null);

  const load = useCallback(async (s) => {
    setLoading(true);
    try {
      const r = await api.get("/admin/improvements", { params: { status: s } });
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load improvements");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(status); }, [status, load]);

  const setItemStatus = async (id, s) => {
    setActingId(id + s);
    try {
      await api.post(`/admin/improvements/${id}/status`, { status: s });
      toast.success(`Marked ${s}`);
      load(status);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update");
    } finally { setActingId(null); }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this improvement permanently?")) return;
    setActingId(id + "del");
    try {
      await api.delete(`/admin/improvements/${id}`);
      toast.success("Deleted");
      load(status);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    } finally { setActingId(null); }
  };

  return (
    <div data-testid="admin-improvements-panel">
      <p className="prose-serif text-sm text-muted-ink mb-6 max-w-prose">
        User-submitted notes from the "Suggest an improvement" widget. Triage as you go.
      </p>
      <div className="flex items-center gap-4 mb-8 border-b hairline overflow-x-auto">
        {STATUSES.map((s) => (
          <button
            key={s}
            data-testid={`improvements-tab-${s}`}
            onClick={() => setStatus(s)}
            className={`pb-3 font-sans text-sm font-medium transition-colors whitespace-nowrap ${
              status === s ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"
            }`}
          >
            {s[0].toUpperCase() + s.slice(1)}
            <span className="ml-2 font-mono text-[10px] text-muted-ink">{counts[s] ?? 0}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="improvements-empty">
          <p className="font-serif text-base ink/80">Nothing in {status}.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {items.map((it) => (
            <article
              key={it.id}
              data-testid={`improvement-${it.id}`}
              className="border hairline rounded-sm p-5 bg-cream"
            >
              <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2 flex-wrap">
                  {it.category && (
                    <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold border border-gold/40 px-2 py-0.5 rounded-sm">
                      {it.category}
                    </span>
                  )}
                  <span className="font-sans text-xs text-muted-ink">
                    {it.submitter_name || it.submitter_email || "anonymous"}
                  </span>
                  {it.page_path && (
                    <span className="font-mono text-[11px] text-muted-ink">
                      {it.page_path}
                    </span>
                  )}
                </div>
                <div className="font-sans text-xs text-muted-ink">{new Date(it.created_at).toLocaleString()}</div>
              </div>
              <p className="prose-serif text-base ink/90 leading-relaxed whitespace-pre-wrap mb-4">
                {it.text}
              </p>
              <div className="flex items-center gap-2 pt-3 border-t hairline flex-wrap">
                {STATUSES.filter((s) => s !== status).map((s) => (
                  <button
                    key={s}
                    data-testid={`improvement-set-${s}-${it.id}`}
                    onClick={() => setItemStatus(it.id, s)}
                    disabled={actingId === it.id + s}
                    className="font-sans text-xs uppercase tracking-wider font-semibold border hairline px-3 py-1.5 rounded-sm hover:bg-gold hover:text-cream hover:border-gold transition-colors disabled:opacity-40"
                  >
                    Mark {s}
                  </button>
                ))}
                <div className="flex-1" />
                <button
                  data-testid={`improvement-delete-${it.id}`}
                  onClick={() => remove(it.id)}
                  disabled={actingId === it.id + "del"}
                  className="font-sans text-xs uppercase tracking-wider font-semibold text-deepred hover:opacity-80 transition-opacity disabled:opacity-40"
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
