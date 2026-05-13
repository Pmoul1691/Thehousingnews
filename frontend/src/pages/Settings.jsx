import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Settings() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState({ am: true, pm: true });
  const [fetching, setFetching] = useState(true);
  const [saving, setSaving] = useState(false);
  const [invites, setInvites] = useState(null);
  const [genBusy, setGenBusy] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    Promise.all([
      api.get("/me/digest-prefs").then((r) => setPrefs({ am: r.data.am !== false, pm: r.data.pm !== false })),
      api.get("/me/invites").then((r) => setInvites(r.data)).catch(() => setInvites(null)),
    ]).finally(() => setFetching(false));
  }, [user, loading, navigate]);

  const save = async (next) => {
    setSaving(true);
    try {
      await api.put("/me/digest-prefs", next);
      setPrefs(next);
      toast.success("Saved");
    } catch (e) {
      toast.error("Could not save");
    } finally { setSaving(false); }
  };

  const generate = async () => {
    setGenBusy(true);
    try {
      await api.post("/me/invites");
      const r = await api.get("/me/invites");
      setInvites(r.data);
      toast.success("Code generated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not generate");
    } finally { setGenBusy(false); }
  };

  const copy = (code) => {
    navigator.clipboard.writeText(code).then(
      () => toast.success("Copied"),
      () => toast.error("Could not copy"),
    );
  };

  const revoke = async (code) => {
    try {
      await api.delete(`/me/invites/${code}`);
      const r = await api.get("/me/invites");
      setInvites(r.data);
      toast.success("Revoked");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not revoke");
    }
  };

  return (
    <div className="container-prose py-16">
      <p className="uppercase-label mb-3">Settings</p>
      <h1 className="font-display font-semibold text-3xl ink mb-2">Inbox preferences.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-10">
        Two digest emails a day, after each release window. Turn off either one. You can turn them back on whenever.
      </p>

      {fetching ? (
        <div className="font-serif text-base text-muted-ink">Loading.</div>
      ) : (
        <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
          <ToggleRow label="Morning digest" hint="Sent after the 8:30am Chicago release." checked={prefs.am} disabled={saving} onChange={(v) => save({ ...prefs, am: v })} testid="toggle-am" />
          <ToggleRow label="Evening digest" hint="Sent after the 5:30pm Chicago release." checked={prefs.pm} disabled={saving} onChange={(v) => save({ ...prefs, pm: v })} testid="toggle-pm" />
        </div>
      )}

      {invites && (
        <section className="mt-16" data-testid="invites-section">
          <p className="uppercase-label mb-3">Invitations</p>
          <h2 className="font-display font-semibold text-2xl ink mb-2">Bring someone in.</h2>
          <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-6">
            Two invite codes per quarter. Each code is one-time-use and expires after sixty days. Pete still reviews every application, but a valid code tells him you vouch for the person.
          </p>

          <div className="border hairline rounded-sm bg-cream p-5 mb-6 flex items-center justify-between gap-4 flex-wrap" data-testid="invites-quota">
            <div>
              <div className="font-sans text-xs uppercase tracking-wider text-muted-ink font-semibold">{invites.quarter}</div>
              <div className="font-display font-semibold text-lg ink mt-1">
                {invites.remaining} of {invites.max_per_quarter} codes left
              </div>
            </div>
            <button
              data-testid="invites-generate"
              onClick={generate}
              disabled={genBusy || invites.remaining <= 0}
              className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {genBusy ? "Generating..." : "Generate code"}
            </button>
          </div>

          {invites.items.length === 0 ? (
            <p className="font-serif text-sm text-muted-ink italic" data-testid="invites-empty">
              You have not generated any codes this quarter.
            </p>
          ) : (
            <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="invites-list">
              {invites.items.map((c) => {
                const used = !!c.redeemed_by_user_id;
                const expired = !used && c.expires_at && c.expires_at < new Date().toISOString();
                return (
                  <div key={c.code} data-testid={`invite-${c.code}`} className="px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
                    <div className="min-w-0">
                      <div className="font-display font-semibold text-base ink tracking-widest">{c.code}</div>
                      <div className="font-sans text-xs text-muted-ink mt-0.5">
                        {used ? (
                          <>Redeemed by {c.redeemed_by_email} on {new Date(c.redeemed_at).toLocaleDateString()}</>
                        ) : expired ? (
                          <>Expired</>
                        ) : (
                          <>Expires {new Date(c.expires_at).toLocaleDateString()}</>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {!used && !expired && (
                        <>
                          <button
                            data-testid={`invite-copy-${c.code}`}
                            onClick={() => copy(c.code)}
                            className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity px-2"
                          >
                            Copy
                          </button>
                          <button
                            data-testid={`invite-revoke-${c.code}`}
                            onClick={() => revoke(c.code)}
                            className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors px-2"
                          >
                            Revoke
                          </button>
                        </>
                      )}
                      {used && <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm">Used</span>}
                      {expired && <span className="font-sans text-[10px] uppercase tracking-wide text-deepred border border-deepred px-1.5 py-0.5 rounded-sm">Expired</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function ToggleRow({ label, hint, checked, onChange, disabled, testid }) {
  return (
    <div className="flex items-center justify-between gap-6 px-5 py-5">
      <div>
        <div className="font-display font-semibold text-base ink">{label}</div>
        <div className="font-sans text-sm text-muted-ink mt-1">{hint}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        data-testid={testid}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${checked ? "bg-gold" : "bg-[#E8D4A0]"}`}
      >
        <span className={`inline-block h-5 w-5 transform rounded-full bg-cream transition-transform ${checked ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    </div>
  );
}
