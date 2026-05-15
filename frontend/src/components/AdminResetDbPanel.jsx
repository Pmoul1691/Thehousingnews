import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Admin-only "Danger zone" tool that wipes member-generated content from the
 * preview DB while preserving admin accounts, the aggregator, and the
 * Substack archive. Requires the operator to type RESET literally.
 */
export default function AdminResetDbPanel() {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/preview-db/preview");
      setPreview(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load preview");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const reset = async () => {
    if (confirm.trim() !== "RESET") return;
    setBusy(true);
    try {
      const r = await api.post("/admin/preview-db/reset", { confirm: "RESET" });
      const total = Object.values(r.data?.deleted || {}).reduce((a, b) => a + (b || 0), 0);
      toast.success(`Reset complete. ${total} rows deleted.`);
      setOpen(false);
      setConfirm("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reset failed");
    } finally { setBusy(false); }
  };

  if (loading || !preview) {
    return (
      <div className="font-serif text-base text-muted-ink py-12 text-center">Loading preview.</div>
    );
  }

  const delTotal = Object.values(preview.will_delete || {}).reduce((a, b) => a + b, 0);

  return (
    <section data-testid="admin-reset-db-panel" className="mt-16 border-t-2 border-deepred/40 pt-8">
      <p className="uppercase-label text-deepred mb-3">Danger zone</p>
      <h2 className="font-display font-semibold text-xl ink mb-2">Reset preview database</h2>
      <p className="prose-serif text-sm text-muted-ink mb-6 max-w-prose">
        Wipes member-generated content (applications, profiles, posts, follows, drafts, etc.) but
        preserves admin accounts, the aggregator (publishers + articles), and the Substack archive.
        Use only on preview / staging.
      </p>

      {!preview.enabled && (
        <div className="border border-deepred bg-deepred/5 rounded-sm p-4 mb-6 font-sans text-sm text-deepred" data-testid="admin-reset-disabled">
          DB reset is disabled in this environment (<code className="font-mono text-xs">AGG_ALLOW_DB_RESET</code> is off).
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-6 mb-6">
        <div>
          <p className="uppercase-label mb-2">Will preserve</p>
          <ul className="space-y-1 font-sans text-sm ink/85">
            <li>Admin users ({preview.preserves?.admin_users?.length || 0})</li>
            <li>Substack-imported essays ({preview.preserves?.substack_imports || 0})</li>
            <li>Aggregator publishers ({preview.preserves?.aggregator_publishers || 0})</li>
            <li>Aggregator articles ({preview.preserves?.aggregator_articles || 0})</li>
          </ul>
        </div>
        <div>
          <p className="uppercase-label mb-2">Will delete ({delTotal} total)</p>
          <ul className="space-y-1 font-sans text-sm ink/85 max-h-40 overflow-auto pr-2">
            {Object.entries(preview.will_delete || {})
              .filter(([, v]) => v > 0)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => (
                <li key={k} className="flex justify-between gap-3">
                  <span className="text-muted-ink">{k}</span>
                  <span className="font-mono text-xs">{v}</span>
                </li>
              ))}
            {delTotal === 0 && <li className="text-muted-ink italic">Nothing to delete.</li>}
          </ul>
        </div>
      </div>

      {!open ? (
        <button
          type="button"
          data-testid="admin-reset-open"
          onClick={() => setOpen(true)}
          disabled={!preview.enabled || delTotal === 0}
          className="border border-deepred text-deepred font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:bg-deepred hover:text-cream transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Reset preview DB...
        </button>
      ) : (
        <div className="border border-deepred bg-cream rounded-sm p-5" data-testid="admin-reset-confirm">
          <p className="font-sans text-sm ink mb-3">
            Type <code className="font-mono text-xs bg-deepred/10 px-1.5 py-0.5 rounded-sm">RESET</code> to confirm.
            This cannot be undone.
          </p>
          <div className="flex items-center gap-3">
            <input
              data-testid="admin-reset-input"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="RESET"
              className="flex-1 max-w-xs bg-cream border border-deepred rounded-sm p-2 font-mono text-sm ink uppercase tracking-widest focus:outline-none focus:ring-1 focus:ring-deepred"
            />
            <button
              type="button"
              data-testid="admin-reset-confirm-btn"
              onClick={reset}
              disabled={confirm.trim() !== "RESET" || busy}
              className="bg-deepred text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busy ? "Resetting." : "Reset now"}
            </button>
            <button
              type="button"
              data-testid="admin-reset-cancel"
              onClick={() => { setOpen(false); setConfirm(""); }}
              disabled={busy}
              className="border hairline font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:bg-gold-mid transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
