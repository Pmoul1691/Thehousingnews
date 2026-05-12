import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Admin() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("pending");
  const [items, setItems] = useState([]);
  const [fetching, setFetching] = useState(false);
  const [actingId, setActingId] = useState(null);

  const load = useCallback(async (status) => {
    setFetching(true);
    try {
      const r = await api.get(`/applications?status=${status}`);
      setItems(r.data.items || []);
    } finally { setFetching(false); }
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (!user.is_admin) { navigate("/feed", { replace: true }); return; }
    load(tab);
  }, [user, loading, navigate, load, tab]);

  const act = async (app_id, kind) => {
    setActingId(app_id + kind);
    try {
      await api.post(`/applications/${app_id}/${kind}`, { note: null });
      toast.success(`Application ${kind}d`);
      load(tab);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    } finally {
      setActingId(null);
    }
  };

  return (
    <div className="container-wide py-12">
      <p className="uppercase-label mb-3">Admin</p>
      <h1 className="font-display font-semibold text-3xl ink mb-8">Application queue</h1>

      <div className="flex items-center gap-4 mb-10 border-b hairline">
        {["pending", "approved", "declined"].map((t) => (
          <button
            key={t}
            data-testid={`admin-tab-${t}`}
            onClick={() => setTab(t)}
            className={`pb-3 font-sans text-sm font-medium transition-colors ${tab === t ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {fetching ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="admin-empty">
          <p className="font-serif text-base ink/80">Nothing in {tab}.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {items.map((a) => (
            <article key={a.application_id} data-testid={`admin-app-${a.application_id}`} className="border hairline rounded-sm p-6 bg-cream">
              <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
                <div>
                  <h3 className="font-display font-semibold text-lg ink">{a.name}</h3>
                  <div className="font-sans text-sm text-muted-ink">{a.email}</div>
                </div>
                <div className="font-sans text-xs text-muted-ink">{new Date(a.created_at).toLocaleString()}</div>
              </div>
              <dl className="grid sm:grid-cols-3 gap-4 mb-4 text-sm">
                <div><dt className="uppercase-label mb-1">Role</dt><dd className="font-serif ink">{a.current_role}</dd></div>
                <div><dt className="uppercase-label mb-1">Market</dt><dd className="font-serif ink">{a.market}</dd></div>
                <div><dt className="uppercase-label mb-1">Years</dt><dd className="font-serif ink">{a.years_in_real_estate}</dd></div>
              </dl>
              <div className="mb-4">
                <dt className="uppercase-label mb-1">Why</dt>
                <dd className="prose-serif text-base ink/90 leading-relaxed whitespace-pre-wrap">{a.why_joining}</dd>
              </div>
              {tab === "pending" && (
                <div className="flex items-center gap-3 pt-4 border-t hairline">
                  <button
                    data-testid={`admin-approve-${a.application_id}`}
                    onClick={() => act(a.application_id, "approve")}
                    disabled={actingId === a.application_id + "approve"}
                    className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    data-testid={`admin-decline-${a.application_id}`}
                    onClick={() => act(a.application_id, "decline")}
                    disabled={actingId === a.application_id + "decline"}
                    className="border border-deepred text-deepred font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:bg-deepred hover:text-cream transition-colors disabled:opacity-50"
                  >
                    Decline
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
