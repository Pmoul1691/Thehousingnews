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
    invite_code: "",
  });
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [inviteState, setInviteState] = useState(null); // {ok, owner_name} | {error}
  const [validating, setValidating] = useState(false);

  const validateInvite = async () => {
    const code = (form.invite_code || "").trim().toUpperCase();
    if (!code) { setInviteState(null); return; }
    setValidating(true);
    try {
      const r = await api.post("/invite/validate", { code });
      setInviteState({ ok: true, owner_name: r.data.owner_name });
    } catch (e) {
      setInviteState({ ok: false, error: e?.response?.data?.detail || "Invalid code" });
    } finally { setValidating(false); }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (form.why_joining.length < 20) {
      toast.error("Tell us a bit more in the last question. At least 20 characters.");
      return;
    }
    if (!acceptTerms) {
      toast.error("Please accept the Terms of Service to continue.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = { ...form };
      payload.invite_code = (form.invite_code || "").trim().toUpperCase() || null;
      await api.post("/applications", payload);
      await refresh();
      navigate("/pending", { replace: true });
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = Array.isArray(d) ? d.map((x) => x?.msg || JSON.stringify(x)).join("; ") : (d || "Could not submit. Try again.");
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container-prose py-20 animate-fade-up">
      <p className="uppercase-label mb-4">Application</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">Tell us about you.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed mb-10 max-w-prose">
        We read every application personally. Keep it short. You will hear from us within 48 hours.
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

        <div>
          <label className="block font-sans text-sm font-semibold ink mb-2">Invite code (optional)</label>
          <p className="font-serif text-sm text-muted-ink mb-2">If a member sent you here, paste their code.</p>
          <div className="flex items-center gap-2">
            <input
              data-testid="apply-invite-code"
              value={form.invite_code}
              onChange={(e) => { setForm({ ...form, invite_code: e.target.value }); setInviteState(null); }}
              onBlur={validateInvite}
              maxLength={32}
              placeholder="ABCD1234"
              className="flex-1 bg-cream border hairline rounded-sm p-3 font-sans text-sm ink tracking-widest uppercase focus:outline-none focus:ring-1 focus:ring-gold"
            />
            <button
              type="button"
              data-testid="apply-invite-validate"
              onClick={validateInvite}
              disabled={validating || !form.invite_code.trim()}
              className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 disabled:opacity-40 transition-opacity px-3 py-2"
            >
              {validating ? "Checking..." : "Check"}
            </button>
          </div>
          {inviteState && inviteState.ok && (
            <p data-testid="apply-invite-ok" className="font-sans text-xs text-gold mt-2">Valid. Invited by {inviteState.owner_name}.</p>
          )}
          {inviteState && inviteState.ok === false && (
            <p data-testid="apply-invite-error" className="font-sans text-xs text-deepred mt-2">{inviteState.error}</p>
          )}
        </div>

        <div className="border-t hairline pt-6">
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              data-testid="apply-accept-terms"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
              className="mt-1 h-4 w-4 accent-gold cursor-pointer shrink-0"
            />
            <span className="font-serif text-sm ink/85 leading-relaxed">
              I have read and agree to The Housing News{" "}
              <a
                href="/legal/terms-of-service.pdf"
                target="_blank"
                rel="noreferrer"
                data-testid="apply-terms-link"
                className="text-gold underline underline-offset-4 decoration-gold-mid hover:opacity-80 transition-opacity"
              >
                Terms of Service
              </a>
              .
            </span>
          </label>
        </div>

        <button
          type="submit"
          disabled={submitting || !acceptTerms}
          data-testid="apply-submit"
          className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
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
