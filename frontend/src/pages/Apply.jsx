import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Apply() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    current_role: "",
    market: "",
    years_in_real_estate: "",
    why_joining: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (form.why_joining.length < 20) {
      toast.error("Tell me a bit more in the last question. At least 20 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/applications", form);
      await refresh();
      navigate("/pending", { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not submit. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container-prose py-20 animate-fade-up">
      <p className="uppercase-label mb-4">Application</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">Tell me about you.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed mb-10 max-w-prose">
        I read every application personally. Keep it short. You will hear from me within 48 hours.
      </p>

      <form onSubmit={submit} className="space-y-8" data-testid="application-form">
        <Field
          label="What do you do in real estate?"
          hint="One sentence. Agent, team lead, broker owner, investor, etc."
          name="current_role"
          value={form.current_role}
          onChange={(v) => setForm({ ...form, current_role: v })}
          testid="apply-current-role"
        />
        <Field
          label="What market do you work in?"
          hint="City and state."
          name="market"
          value={form.market}
          onChange={(v) => setForm({ ...form, market: v })}
          testid="apply-market"
        />
        <Field
          label="How many years in the business?"
          hint="A number is fine."
          name="years_in_real_estate"
          value={form.years_in_real_estate}
          onChange={(v) => setForm({ ...form, years_in_real_estate: v })}
          testid="apply-years"
        />
        <div>
          <label className="block font-sans text-sm font-semibold ink mb-2">Why do you want in?</label>
          <p className="font-serif text-sm text-muted-ink mb-2">A short paragraph. Plain words.</p>
          <textarea
            data-testid="apply-why"
            className="w-full bg-cream border hairline rounded-sm p-3 font-serif text-base ink focus:outline-none focus:ring-1 focus:ring-gold min-h-[140px]"
            value={form.why_joining}
            onChange={(e) => setForm({ ...form, why_joining: e.target.value })}
            maxLength={600}
          />
          <div className="text-right font-sans text-xs text-muted-ink mt-1">{form.why_joining.length}/600</div>
        </div>

        <button
          type="submit"
          disabled={submitting}
          data-testid="apply-submit"
          className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {submitting ? "Submitting..." : "Send application"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, hint, value, onChange, testid }) {
  return (
    <div>
      <label className="block font-sans text-sm font-semibold ink mb-2">{label}</label>
      {hint && <p className="font-serif text-sm text-muted-ink mb-2">{hint}</p>}
      <input
        data-testid={testid}
        className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
