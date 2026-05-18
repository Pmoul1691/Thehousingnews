import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

export default function AdminAdminsPanel() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [actingId, setActingId] = useState(null);

  const search = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/users/search", { params: { q, limit: 50 } });
      setItems(r.data?.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not search users");
    } finally { setLoading(false); }
  }, [q]);

  // Initial load with empty query (shows existing admins first)
  useEffect(() => { search(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, []);

  const setAdmin = async (u, makeAdmin) => {
    const verb = makeAdmin ? "promote" : "demote";
    if (!window.confirm(`${verb === "promote" ? "Promote" : "Demote"} ${u.email || u.name}?`)) return;
    setActingId(u.user_id + verb);
    try {
      await api.post(`/admin/users/${u.user_id}/promote`, { is_admin: makeAdmin });
      toast.success(`${u.name || u.email} ${makeAdmin ? "is now an admin" : "is no longer an admin"}`);
      search();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update");
    } finally { setActingId(null); }
  };

  return (
    <div data-testid="admin-admins-panel">
      <p className="prose-serif text-sm text-muted-ink mb-6 max-w-prose">
        Grant or revoke admin access. Env-config admins (set via <code className="font-mono text-[12px]">ADMIN_EMAILS</code>)
        are always admin and cannot be demoted from here.
      </p>

      <form
        onSubmit={(e) => { e.preventDefault(); search(); }}
        className="flex items-center gap-2 mb-6"
      >
        <input
          data-testid="admins-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by email or name…"
          className="flex-1 max-w-sm bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <button
          type="submit"
          className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity px-3 py-2"
        >
          Search
        </button>
      </form>

      {loading ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="admins-empty">
          <p className="font-serif text-base ink/80">No users match.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((u) => (
            <article
              key={u.user_id}
              data-testid={`admin-user-${u.user_id}`}
              className="border hairline rounded-sm p-4 bg-cream flex items-center justify-between gap-4 flex-wrap"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-display font-semibold text-base ink truncate">{u.name || "—"}</h3>
                  {u.is_admin && (
                    <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold border border-gold/40 px-2 py-0.5 rounded-sm">
                      {u.env_admin ? "Env admin" : "Admin"}
                    </span>
                  )}
                  {u.suspended && (
                    <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-deepred border border-deepred/40 px-2 py-0.5 rounded-sm">
                      Suspended
                    </span>
                  )}
                </div>
                <div className="font-sans text-xs text-muted-ink truncate">{u.email}</div>
                <div className="font-mono text-[10px] text-muted-ink mt-0.5">{u.status}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {u.env_admin ? (
                  <span className="font-sans text-[11px] italic text-muted-ink">Locked via env</span>
                ) : u.is_admin ? (
                  <button
                    data-testid={`admin-demote-${u.user_id}`}
                    onClick={() => setAdmin(u, false)}
                    disabled={actingId === u.user_id + "demote"}
                    className="font-sans text-xs uppercase tracking-wider font-semibold border border-deepred text-deepred px-3 py-1.5 rounded-sm hover:bg-deepred hover:text-cream transition-colors disabled:opacity-40"
                  >
                    Demote
                  </button>
                ) : (
                  <button
                    data-testid={`admin-promote-${u.user_id}`}
                    onClick={() => setAdmin(u, true)}
                    disabled={actingId === u.user_id + "promote"}
                    className="bg-gold text-cream font-sans font-semibold text-xs uppercase tracking-wider px-3 py-1.5 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40"
                  >
                    Promote
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
