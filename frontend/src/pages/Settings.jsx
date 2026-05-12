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

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    api.get("/me/digest-prefs")
      .then((r) => setPrefs({ am: r.data.am !== false, pm: r.data.pm !== false }))
      .finally(() => setFetching(false));
  }, [user, loading, navigate]);

  const save = async (next) => {
    setSaving(true);
    try {
      await api.put("/me/digest-prefs", next);
      setPrefs(next);
      toast.success("Saved");
    } catch (e) {
      toast.error("Could not save");
    } finally {
      setSaving(false);
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
          <ToggleRow
            label="Morning digest"
            hint="Sent after the 8:30am Chicago release."
            checked={prefs.am}
            disabled={saving}
            onChange={(v) => save({ ...prefs, am: v })}
            testid="toggle-am"
          />
          <ToggleRow
            label="Evening digest"
            hint="Sent after the 5:30pm Chicago release."
            checked={prefs.pm}
            disabled={saving}
            onChange={(v) => save({ ...prefs, pm: v })}
            testid="toggle-pm"
          />
        </div>
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
