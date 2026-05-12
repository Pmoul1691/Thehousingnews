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
  });
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    api.get("/profile").then((r) => {
      if (r.data && r.data.user_id) {
        setForm({
          name: r.data.name || user?.name || "",
          market: r.data.market || "",
          bio: r.data.bio || "",
          avatar_path: r.data.avatar_path || "",
          objectives: r.data.objectives && r.data.objectives.length === 3 ? r.data.objectives : ["", "", ""],
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
