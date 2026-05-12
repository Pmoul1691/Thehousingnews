import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Admin() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [section, setSection] = useState("apps");
  const [appsTab, setAppsTab] = useState("pending");
  const [flagsTab, setFlagsTab] = useState("open");
  const [apps, setApps] = useState([]);
  const [flags, setFlags] = useState([]);
  const [fetching, setFetching] = useState(false);
  const [actingId, setActingId] = useState(null);

  const loadApps = useCallback(async (status) => {
    setFetching(true);
    try {
      const r = await api.get(`/applications?status=${status}`);
      setApps(r.data.items || []);
    } finally { setFetching(false); }
  }, []);

  const loadFlags = useCallback(async (status) => {
    setFetching(true);
    try {
      const r = await api.get(`/admin/flags?status=${status}`);
      setFlags(r.data.items || []);
    } finally { setFetching(false); }
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (!user.is_admin) { navigate("/feed", { replace: true }); return; }
    if (section === "apps") loadApps(appsTab);
    else loadFlags(flagsTab);
  }, [user, loading, navigate, section, appsTab, flagsTab, loadApps, loadFlags]);

  const actApp = async (app_id, kind) => {
    setActingId(app_id + kind);
    try {
      await api.post(`/applications/${app_id}/${kind}`, { note: null });
      toast.success(`Application ${kind}d`);
      loadApps(appsTab);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    } finally { setActingId(null); }
  };

  const hideTarget = async (flag) => {
    const url = flag.target_kind === "post"
      ? `/admin/posts/${flag.target_id}/hide`
      : `/admin/replies/${flag.target_id}/hide`;
    setActingId(flag.flag_id + "hide");
    try {
      await api.post(url);
      toast.success("Hidden");
      loadFlags(flagsTab);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not hide");
    } finally { setActingId(null); }
  };

  const dismissFlag = async (flag) => {
    setActingId(flag.flag_id + "dismiss");
    try {
      await api.post(`/admin/flags/${flag.flag_id}/dismiss`);
      toast.success("Flag dismissed");
      loadFlags(flagsTab);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not dismiss");
    } finally { setActingId(null); }
  };

  const suspend = async (owner) => {
    const verb = owner.suspended ? "unsuspend" : "suspend";
    setActingId(owner.user_id + verb);
    try {
      await api.post(`/admin/users/${owner.user_id}/${verb}`);
      toast.success(`Member ${verb}ed`);
      loadFlags(flagsTab);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not " + verb);
    } finally { setActingId(null); }
  };

  return (
    <div className="container-wide py-12">
      <p className="uppercase-label mb-3">Admin</p>
      <h1 className="font-display font-semibold text-3xl ink mb-8">Pete's queue</h1>

      <div className="flex items-center gap-6 mb-8 border-b hairline">
        {[
          { k: "apps", l: "Applications" },
          { k: "mod", l: "Moderation" },
        ].map((t) => (
          <button
            key={t.k}
            data-testid={`admin-section-${t.k}`}
            onClick={() => setSection(t.k)}
            className={`pb-3 font-display font-semibold text-base transition-colors ${section === t.k ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
          >
            {t.l}
          </button>
        ))}
      </div>

      {section === "apps" ? (
        <>
          <div className="flex items-center gap-4 mb-10 border-b hairline">
            {["pending", "approved", "declined"].map((t) => (
              <button
                key={t}
                data-testid={`admin-tab-${t}`}
                onClick={() => setAppsTab(t)}
                className={`pb-3 font-sans text-sm font-medium transition-colors ${appsTab === t ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
              >
                {t[0].toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
          {fetching ? (
            <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
          ) : apps.length === 0 ? (
            <div className="border hairline rounded-sm py-16 text-center" data-testid="admin-empty">
              <p className="font-serif text-base ink/80">Nothing in {appsTab}.</p>
            </div>
          ) : (
            <div className="space-y-8">
              {apps.map((a) => (
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
                  {appsTab === "pending" && (
                    <div className="flex items-center gap-3 pt-4 border-t hairline">
                      <button
                        data-testid={`admin-approve-${a.application_id}`}
                        onClick={() => actApp(a.application_id, "approve")}
                        disabled={actingId === a.application_id + "approve"}
                        className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        data-testid={`admin-decline-${a.application_id}`}
                        onClick={() => actApp(a.application_id, "decline")}
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
        </>
      ) : (
        <>
          <div className="flex items-center gap-4 mb-10 border-b hairline">
            {["open", "resolved"].map((t) => (
              <button
                key={t}
                data-testid={`admin-flags-${t}`}
                onClick={() => setFlagsTab(t)}
                className={`pb-3 font-sans text-sm font-medium transition-colors ${flagsTab === t ? "text-gold border-b-2 border-gold" : "text-muted-ink hover:text-ink"}`}
              >
                {t[0].toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
          {fetching ? (
            <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
          ) : flags.length === 0 ? (
            <div className="border hairline rounded-sm py-16 text-center" data-testid="admin-flags-empty">
              <p className="font-serif text-base ink/80">No {flagsTab} flags.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {flags.map((f) => (
                <article key={f.flag_id} data-testid={`admin-flag-${f.flag_id}`} className="border hairline rounded-sm p-6 bg-cream">
                  <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
                    <div>
                      <div className="font-sans text-xs text-gold uppercase tracking-wide">{f.target_kind} report</div>
                      <h3 className="font-display font-semibold text-base ink mt-1">
                        {f.owner.name} {f.owner.suspended && <span className="font-sans text-xs text-deepred ml-2">suspended</span>}
                      </h3>
                      <div className="font-sans text-xs text-muted-ink">{f.owner.email}</div>
                    </div>
                    <div className="font-sans text-xs text-muted-ink">{new Date(f.created_at).toLocaleString()}</div>
                  </div>
                  {f.reason && (
                    <div className="mb-3">
                      <div className="uppercase-label mb-1">Reporter said</div>
                      <div className="prose-serif text-sm ink/90 leading-relaxed">{f.reason}</div>
                    </div>
                  )}
                  {f.target ? (
                    <div className="mb-3 border-l-2 border-gold-mid pl-4">
                      <div className="uppercase-label mb-1">{f.target_kind === "post" ? "Post" : "Reply"}</div>
                      <div className="prose-serif text-[15px] ink/90 leading-relaxed whitespace-pre-wrap">{f.target.text}</div>
                      {f.target.status === "hidden" && <div className="mt-2 font-sans text-xs text-deepred uppercase tracking-wide">Currently hidden</div>}
                    </div>
                  ) : (
                    <div className="font-sans text-sm text-muted-ink mb-3">Target was deleted.</div>
                  )}
                  {flagsTab === "open" && (
                    <div className="flex items-center gap-3 pt-3 border-t hairline">
                      <Link to={`/profile/${f.target_owner_id}`} className="font-sans text-sm text-muted-ink hover:text-gold underline underline-offset-4 decoration-gold-mid">View author</Link>
                      <div className="flex-1" />
                      <button
                        data-testid={`flag-dismiss-${f.flag_id}`}
                        onClick={() => dismissFlag(f)}
                        disabled={actingId === f.flag_id + "dismiss"}
                        className="border hairline font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:bg-gold-mid transition-colors disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                      {f.target && f.target.status !== "hidden" && (
                        <button
                          data-testid={`flag-hide-${f.flag_id}`}
                          onClick={() => hideTarget(f)}
                          disabled={actingId === f.flag_id + "hide"}
                          className="border border-deepred text-deepred font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:bg-deepred hover:text-cream transition-colors disabled:opacity-50"
                        >
                          Hide {f.target_kind}
                        </button>
                      )}
                      <button
                        data-testid={`flag-suspend-${f.flag_id}`}
                        onClick={() => suspend(f.owner)}
                        disabled={actingId === f.owner.user_id + (f.owner.suspended ? "unsuspend" : "suspend")}
                        className="bg-deepred text-cream font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                      >
                        {f.owner.suspended ? "Unsuspend" : "Suspend"}
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
