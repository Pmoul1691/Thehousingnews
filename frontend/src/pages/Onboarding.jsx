import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Onboarding() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: user?.name || "",
    market: "",
    bio: "",
    avatar_path: "",
    objectives: ["", "", ""],
    linkedin_url: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importedCareer, setImportedCareer] = useState(null);

  useEffect(() => {
    api.get("/profile").then((r) => {
      if (r.data && r.data.user_id) {
        setForm({
          name: r.data.name || user?.name || "",
          market: r.data.market || "",
          bio: r.data.bio || "",
          avatar_path: r.data.avatar_path || "",
          objectives: r.data.objectives && r.data.objectives.length === 3 ? r.data.objectives : ["", "", ""],
          linkedin_url: r.data.linkedin_url || "",
        });
      }
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setObjective = (i, v) => {
    const next = [...form.objectives];
    next[i] = v;
    setForm({ ...form, objectives: next });
  };

  const onUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "avatars");
      const r = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm({ ...form, avatar_path: r.data.path });
      toast.success("Avatar uploaded");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const importFromLinkedIn = async () => {
    const url = (form.linkedin_url || "").trim();
    if (!url) { toast.error("Paste your LinkedIn URL first"); return; }
    setImporting(true);
    try {
      const r = await api.post("/profile/linkedin-import", { linkedin_url: url });
      const s = r.data?.suggested || {};
      setForm((prev) => ({
        ...prev,
        // Only fill blanks — never overwrite what the member already typed.
        name: prev.name?.trim() ? prev.name : (s.name || prev.name),
        market: prev.market?.trim() ? prev.market : (s.market || prev.market),
        bio: prev.bio?.trim() ? prev.bio : (s.bio || prev.bio),
        linkedin_url: r.data?.linkedin_url || prev.linkedin_url,
      }));
      setImportedCareer(r.data?.career || null);
      toast.success("Imported from LinkedIn");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "LinkedIn import failed");
    } finally {
      setImporting(false);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    const objectives = form.objectives.map((s) => s.trim());
    if (objectives.some((s) => !s)) { toast.error("Write all three objectives."); return; }
    if (!form.market.trim()) { toast.error("Market is required."); return; }
    if (!form.name.trim()) { toast.error("Name is required."); return; }
    setSubmitting(true);
    try {
      await api.put("/profile", { ...form, objectives });
      await refresh();
      toast.success("Profile saved");
      navigate("/feed");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally {
      setSubmitting(false);
    }
  };

  const avatarUrl = form.avatar_path ? `${API}/uploads/file/${form.avatar_path}` : null;

  return (
    <div className="container-prose py-16 animate-fade-up">
      <p className="uppercase-label mb-4">Set up your profile</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-4">Three things to write.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed mb-10 max-w-prose">
        Your bio. Where you work. And exactly three objectives you are pushing on this quarter. You can revise the objectives anytime. I keep prior versions.
      </p>

      <form onSubmit={save} className="space-y-10" data-testid="onboarding-form">
        <div className="flex items-center gap-6">
          <div className="w-20 h-20 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center">
            {avatarUrl ? (
              <img src={avatarUrl} alt="avatar" className="w-full h-full object-cover" />
            ) : (
              <span className="font-display text-2xl text-gold">{(form.name || "P")[0]}</span>
            )}
          </div>
          <label className="cursor-pointer font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
            {uploading ? "Uploading..." : "Upload photo"}
            <input data-testid="upload-avatar" type="file" accept="image/*" className="hidden" onChange={(e) => onUpload(e.target.files?.[0])} />
          </label>
        </div>

        <Field label="Your name" testid="onb-name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
        <Field label="Market (city, state)" testid="onb-market" value={form.market} onChange={(v) => setForm({ ...form, market: v })} />

        <div>
          <label className="block font-sans text-sm font-semibold ink mb-2">Bio</label>
          <p className="font-serif text-sm text-muted-ink mb-2">280 characters. Plain words.</p>
          <textarea
            data-testid="onb-bio"
            className="w-full bg-cream border hairline rounded-sm p-3 font-serif text-base ink focus:outline-none focus:ring-1 focus:ring-gold min-h-[100px]"
            value={form.bio}
            maxLength={280}
            onChange={(e) => setForm({ ...form, bio: e.target.value })}
          />
          <div className="text-right font-sans text-xs text-muted-ink mt-1">{form.bio.length}/280</div>
        </div>

        <div>
          <label className="block font-sans text-sm font-semibold ink mb-2">Three public objectives</label>
          <p className="font-serif text-sm text-muted-ink mb-3">Specific. One sentence each.</p>
          {[0, 1, 2].map((i) => (
            <input
              key={i}
              data-testid={`onb-objective-${i + 1}`}
              className="block w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold mb-3"
              placeholder={`Objective ${i + 1}`}
              maxLength={140}
              value={form.objectives[i]}
              onChange={(e) => setObjective(i, e.target.value)}
            />
          ))}
        </div>

        <div>
          <label className="block font-sans text-sm font-semibold ink mb-2">LinkedIn (optional)</label>
          <p className="font-serif text-sm text-muted-ink mb-3">
            Paste your profile URL or just your handle. It shows up as a small icon next to your name across the site.
          </p>
          <input
            data-testid="onb-linkedin"
            type="text"
            inputMode="url"
            className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
            placeholder="https://www.linkedin.com/in/your-handle"
            maxLength={200}
            value={form.linkedin_url}
            onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })}
          />
          <div className="mt-3 flex items-start gap-3 flex-wrap">
            <button
              type="button"
              onClick={importFromLinkedIn}
              disabled={importing || !form.linkedin_url?.trim()}
              data-testid="onb-linkedin-import"
              className="inline-flex items-center gap-1.5 bg-ink text-cream font-sans font-semibold text-xs uppercase tracking-wider px-3 py-2 rounded-sm hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {importing ? "Importing…" : "Auto-fill from LinkedIn →"}
            </button>
            <p className="font-serif italic text-xs text-muted-ink max-w-xs">
              We&apos;ll fill in any blank fields above (we never overwrite what you&apos;ve typed) and pull your work history into your profile.
            </p>
          </div>
          {importedCareer?.experiences?.length > 0 && (
            <div className="mt-4 bg-cream-soft border border-gold/20 rounded-sm p-4" data-testid="onb-linkedin-career">
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-2">
                Imported from LinkedIn
              </p>
              <ul className="space-y-1.5 font-serif text-sm text-ink/80">
                {importedCareer.experiences.slice(0, 5).map((e, i) => (
                  <li key={i}>
                    <span className="font-semibold ink">{e.title}</span>
                    {e.company ? <> · {e.company}</> : null}
                    {e.starts_at ? <span className="font-mono text-[11px] text-muted-ink ml-2">{e.starts_at}–{e.ends_at || "present"}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <details className="mt-3 group">
            <summary className="cursor-pointer font-sans text-xs text-gold hover:opacity-80 select-none">
              How to copy your LinkedIn URL →
            </summary>
            <ol className="mt-3 space-y-2 font-serif text-sm text-muted-ink leading-relaxed list-decimal pl-5">
              <li>Open <a href="https://www.linkedin.com" target="_blank" rel="noreferrer" className="text-gold underline underline-offset-4">linkedin.com</a> and sign in.</li>
              <li>Click your photo (top right) → <strong>View profile</strong>.</li>
              <li>Copy the URL in your browser's address bar — it'll look like <code className="font-mono text-xs bg-gold/10 px-1.5 rounded-sm">https://www.linkedin.com/in/your-handle</code>.</li>
              <li>Paste it above. We'll clean it up for you.</li>
            </ol>
          </details>
        </div>

        <button
          type="submit"
          disabled={submitting}
          data-testid="onboarding-submit"
          className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {submitting ? "Saving..." : "Save and enter"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, testid, value, onChange }) {
  return (
    <div>
      <label className="block font-sans text-sm font-semibold ink mb-2">{label}</label>
      <input
        data-testid={testid}
        className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
