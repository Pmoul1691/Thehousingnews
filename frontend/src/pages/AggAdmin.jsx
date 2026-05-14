import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const CATEGORIES = ["national_trade", "regional", "industry_blog", "data_research", "mortgage", "commercial_re"];
const DISPLAY_MODES = ["headline_only", "headline_and_snippet"];
const PERMISSION_STATUSES = ["pending", "granted", "declined", "not_required"];

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(d);
}

export default function AggAdmin() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [publishers, setPublishers] = useState([]);
  const [fetching, setFetching] = useState(false);
  const [acting, setActing] = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    setFetching(true);
    try {
      const r = await api.get("/agg/admin/publishers");
      setPublishers(r.data.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load publishers");
    } finally { setFetching(false); }
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (!user.is_admin) { navigate("/", { replace: true }); return; }
    load();
  }, [user, loading, navigate, load]);

  const toggleActive = async (p) => {
    setActing(p.id + "active");
    try {
      await api.patch(`/agg/admin/publishers/${p.id}`, { active: !p.active });
      toast.success(p.active ? "Deactivated" : "Activated");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally { setActing(null); }
  };

  const refreshNow = async (p) => {
    setActing(p.id + "refresh");
    try {
      const r = await api.post(`/agg/admin/publishers/${p.id}/refresh`);
      toast.success(r.data.ok ? `Pulled. ${r.data.inserted} new, ${r.data.skipped} dedup.` : `Failed: ${r.data.reason}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally { setActing(null); }
  };

  return (
    <div data-testid="agg-admin-page">
      <h1 className="font-display font-semibold text-2xl text-agg-navy mb-4">Aggregator admin</h1>
      <p className="text-sm text-slate-500 mb-6">28 publishers seeded. Cron pulls every 15 minutes. Compliance rules (no full text, 90/120-day expiry) are enforced server-side.</p>

      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => setShowAdd((s) => !s)}
          data-testid="agg-admin-toggle-add"
          className="bg-agg-orange text-agg-navy font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity"
        >
          {showAdd ? "Cancel" : "+ Add publisher"}
        </button>
        <button onClick={load} className="font-sans text-sm text-agg-navy hover:text-agg-orange transition-colors">Refresh list</button>
      </div>

      {showAdd && <AddPublisherForm onDone={() => { setShowAdd(false); load(); }} />}

      {fetching ? (
        <p className="text-slate-500 py-10 text-center">Loading.</p>
      ) : (
        <div className="border border-slate-200 rounded-sm overflow-x-auto" data-testid="agg-admin-table">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-[11px] uppercase tracking-wider">
              <tr>
                <th className="text-left px-3 py-2">Publisher</th>
                <th className="text-left px-3 py-2">Category</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Last pull</th>
                <th className="text-right px-3 py-2">Items 7d</th>
                <th className="text-right px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {publishers.map((p) => (
                <tr key={p.id} data-testid={`agg-admin-row-${p.slug}`} className={p.active ? "" : "opacity-60"}>
                  <td className="px-3 py-2">
                    <div className="font-semibold text-agg-navy">{p.name}</div>
                    <div className="text-[11px] text-slate-500">{p.slug}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{p.category.replace("_", " ")}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider ${
                      p.last_fetch_status === "ok" ? "text-emerald-700" :
                      p.last_fetch_status ? "text-red-700" : "text-slate-500"
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${
                        p.last_fetch_status === "ok" ? "bg-emerald-500" :
                        p.last_fetch_status ? "bg-red-500" : "bg-slate-300"
                      }`} />
                      {p.last_fetch_status || "untried"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-600 text-[12px]">{formatTime(p.last_fetched_at)}</td>
                  <td className="px-3 py-2 text-right text-slate-600">{p.items_last_7d || 0}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex items-center gap-2">
                      <button
                        onClick={() => refreshNow(p)}
                        disabled={acting === p.id + "refresh"}
                        data-testid={`agg-admin-refresh-${p.slug}`}
                        className="font-sans text-xs text-agg-navy hover:text-agg-orange disabled:opacity-50 transition-colors"
                      >
                        {acting === p.id + "refresh" ? "..." : "Refresh"}
                      </button>
                      <button
                        onClick={() => toggleActive(p)}
                        disabled={acting === p.id + "active"}
                        data-testid={`agg-admin-toggle-${p.slug}`}
                        className="font-sans text-xs text-agg-navy hover:text-agg-orange disabled:opacity-50 transition-colors"
                      >
                        {p.active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddPublisherForm({ onDone }) {
  const [form, setForm] = useState({
    name: "", slug: "", category: "industry_blog", feed_url: "", homepage_url: "",
    display_mode: "headline_and_snippet", permission_status: "pending", refresh_minutes: 30,
  });
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onTest = async () => {
    if (!form.feed_url) return;
    setBusy(true);
    try {
      const r = await api.post("/agg/admin/test-feed", { feed_url: form.feed_url, display_mode: form.display_mode });
      setTest(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Test failed");
    } finally { setBusy(false); }
  };

  const onCreate = async () => {
    if (!form.name || !form.slug || !form.feed_url) {
      toast.error("Name, slug, and feed URL are required.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/agg/admin/publishers", form);
      toast.success("Created (inactive). Test the feed, then activate.");
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="border border-slate-200 rounded-sm p-5 mb-6 bg-white" data-testid="agg-admin-add-form">
      <h2 className="font-display font-semibold text-lg text-agg-navy mb-4">Add publisher</h2>
      <div className="grid sm:grid-cols-2 gap-3">
        <input data-testid="agg-add-name" placeholder="Display name" value={form.name} onChange={(e) => setField("name", e.target.value)} className="border border-slate-200 rounded-sm px-3 py-2 text-sm" />
        <input data-testid="agg-add-slug" placeholder="slug-no-spaces" value={form.slug} onChange={(e) => setField("slug", e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} className="border border-slate-200 rounded-sm px-3 py-2 text-sm" />
        <input data-testid="agg-add-feed" placeholder="https://example.com/feed/" value={form.feed_url} onChange={(e) => setField("feed_url", e.target.value)} className="sm:col-span-2 border border-slate-200 rounded-sm px-3 py-2 text-sm" />
        <input data-testid="agg-add-homepage" placeholder="Homepage (optional)" value={form.homepage_url} onChange={(e) => setField("homepage_url", e.target.value)} className="sm:col-span-2 border border-slate-200 rounded-sm px-3 py-2 text-sm" />
        <select data-testid="agg-add-category" value={form.category} onChange={(e) => setField("category", e.target.value)} className="border border-slate-200 rounded-sm px-3 py-2 text-sm">
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select data-testid="agg-add-display-mode" value={form.display_mode} onChange={(e) => setField("display_mode", e.target.value)} className="border border-slate-200 rounded-sm px-3 py-2 text-sm">
          {DISPLAY_MODES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select data-testid="agg-add-permission" value={form.permission_status} onChange={(e) => setField("permission_status", e.target.value)} className="border border-slate-200 rounded-sm px-3 py-2 text-sm">
          {PERMISSION_STATUSES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input data-testid="agg-add-refresh" type="number" min="5" max="720" value={form.refresh_minutes} onChange={(e) => setField("refresh_minutes", Number(e.target.value))} className="border border-slate-200 rounded-sm px-3 py-2 text-sm" placeholder="Refresh minutes" />
      </div>

      <div className="mt-4 flex gap-3">
        <button onClick={onTest} disabled={busy || !form.feed_url} data-testid="agg-add-test" className="font-sans text-sm text-agg-navy border border-agg-navy/30 rounded-sm px-4 py-2 hover:bg-slate-50 transition-colors disabled:opacity-50">Test feed</button>
        <button onClick={onCreate} disabled={busy} data-testid="agg-add-create" className="bg-agg-orange text-agg-navy font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50">Create (inactive)</button>
      </div>

      {test && (
        <div className="mt-5 border-t border-slate-200 pt-4" data-testid="agg-add-test-result">
          {test.ok ? (
            <>
              <p className="font-sans text-xs uppercase tracking-wider text-emerald-700 mb-2">Feed OK · {test.count} items parsed · showing first 3</p>
              <ul className="space-y-2 text-sm">
                {(test.items || []).map((it, i) => (
                  <li key={i}>
                    <div className="font-semibold text-agg-navy">{it.title}</div>
                    {it.snippet && <div className="text-slate-700 text-[13px]">{it.snippet}</div>}
                    <div className="text-[11px] text-slate-500">{it.original_url}</div>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-red-700 text-sm">Feed test failed: {test.reason}</p>
          )}
        </div>
      )}
    </div>
  );
}
