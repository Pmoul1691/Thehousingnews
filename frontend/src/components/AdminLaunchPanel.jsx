import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Admin Launch Panel — one-time public-launch broadcast control.
 *
 * Shows:
 *  - Preview of the rendered HTML (in an iframe sandbox)
 *  - Eligibility counts: total approved members, how many have already received it
 *  - "Send test to me" button — single email to the admin's address
 *  - "Send to all members" gold button — fires the broadcast, idempotent unless force=true
 *  - "Force resend" toggle for admins who want to send a corrected version
 *
 * Backend: /api/admin/launch/preview, /send, /send-test
 */
export default function AdminLaunchPanel() {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/launch/preview");
      setPreview(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load preview");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const sendTest = async (e) => {
    e?.preventDefault?.();
    if (!testEmail.trim() || !testEmail.includes("@")) {
      toast.error("Enter a valid email");
      return;
    }
    setBusy(true);
    try {
      await api.post("/admin/launch/send-test", { email: testEmail.trim() });
      toast.success(`Test sent to ${testEmail.trim()}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Test send failed");
    } finally { setBusy(false); }
  };

  const fire = async () => {
    if (confirmText.trim().toUpperCase() !== "LAUNCH") {
      toast.error('Type "LAUNCH" to confirm');
      return;
    }
    setBusy(true);
    try {
      const r = await api.post("/admin/launch/send", { confirm: "LAUNCH", force });
      const { sent, skipped, errors = [] } = r.data;
      if (errors.length > 0) {
        toast.error(`Sent ${sent}, skipped ${skipped}, ${errors.length} errors`);
      } else {
        toast.success(`Broadcast sent to ${sent} members${skipped ? `, skipped ${skipped}` : ""}.`);
      }
      setShowConfirm(false);
      setConfirmText("");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Broadcast failed");
    } finally { setBusy(false); }
  };

  if (loading) {
    return <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>;
  }
  if (!preview) {
    return <div className="font-serif text-base text-muted-ink py-12 text-center">Could not load the preview.</div>;
  }

  const remaining = preview.remaining ?? 0;
  const alreadySent = preview.already_sent ?? 0;
  const total = preview.eligible_total ?? 0;

  return (
    <div className="space-y-8" data-testid="admin-launch-panel">
      <header>
        <p className="uppercase-label mb-2">One-time broadcast</p>
        <h2 className="font-display font-semibold text-2xl ink mb-2">We are live. Welcome to The Housing News.</h2>
        <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose">
          Fires a single styled launch email to every approved, non-suspended member with deep links to The Daily, the Composer, the directory, and this week's subject. Idempotent &mdash; each member receives it once unless you toggle <em>Force resend</em>.
        </p>
      </header>

      {/* Eligibility ---------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="admin-launch-eligibility">
        <div className="border hairline rounded-sm bg-cream p-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-ink">Approved members</div>
          <div className="font-display font-semibold text-3xl ink mt-1" data-testid="launch-eligible">{total}</div>
        </div>
        <div className="border hairline rounded-sm bg-cream p-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-ink">Already received</div>
          <div className="font-display font-semibold text-3xl ink mt-1" data-testid="launch-already-sent">{alreadySent}</div>
        </div>
        <div className="border hairline rounded-sm bg-[#FBF6E8] p-4">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">Remaining</div>
          <div className="font-display font-semibold text-3xl ink mt-1" data-testid="launch-remaining">{remaining}</div>
        </div>
      </div>

      {/* Test send ------------------------------------------------------ */}
      <section className="border hairline rounded-sm bg-cream p-5">
        <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mb-2">Test first</p>
        <p className="font-serif text-sm ink/80 mb-4">
          Send yourself a copy &mdash; the subject is prefixed with <code className="font-mono text-[12px] bg-white px-1 py-0.5 rounded-sm">[TEST]</code>, no dispatch row is recorded, and the recipient doesn&apos;t count toward the broadcast.
        </p>
        <form onSubmit={sendTest} className="flex items-center gap-2 flex-wrap" data-testid="launch-test-form">
          <input
            type="email"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            placeholder="you@example.com"
            data-testid="launch-test-email"
            className="flex-1 min-w-[220px] border hairline bg-white rounded-sm px-3 py-2 font-sans text-sm focus:outline-none focus:border-gold"
          />
          <button
            type="submit"
            disabled={busy}
            data-testid="launch-test-send-btn"
            className="font-sans font-semibold text-sm border border-gold text-gold px-4 py-2 rounded-sm hover:bg-gold hover:text-cream transition-colors disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send test to me"}
          </button>
        </form>
      </section>

      {/* Broadcast ------------------------------------------------------ */}
      <section className="border hairline rounded-sm bg-[#FBF6E8] p-5">
        <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mb-2">Broadcast</p>
        <p className="font-serif text-sm ink/80 mb-4">
          {remaining > 0 ? (
            <>This will send to <strong>{remaining}</strong> approved member{remaining === 1 ? "" : "s"}.</>
          ) : (
            <>Every approved member has already received the launch broadcast.</>
          )}
        </p>

        <label className="flex items-center gap-2 mb-4 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
            data-testid="launch-force-toggle"
            className="accent-gold"
          />
          <span className="font-sans text-sm ink">Force resend &mdash; ignore the already-received list (use only if you changed the copy and want everyone to see it again)</span>
        </label>

        {!showConfirm ? (
          <button
            type="button"
            onClick={() => setShowConfirm(true)}
            disabled={busy || (!force && remaining === 0)}
            data-testid="launch-fire-btn"
            className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            Send to all members
          </button>
        ) : (
          <div className="border border-deepred rounded-sm bg-white p-4" data-testid="launch-confirm-box">
            <p className="font-serif text-sm ink mb-3">
              Type <strong className="font-mono">LAUNCH</strong> below to confirm. This sends real email through Brevo and cannot be undone.
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="LAUNCH"
                autoFocus
                data-testid="launch-confirm-input"
                className="flex-1 min-w-[120px] border hairline bg-white rounded-sm px-3 py-2 font-mono text-sm focus:outline-none focus:border-deepred uppercase"
              />
              <button
                type="button"
                onClick={fire}
                disabled={busy || confirmText.trim().toUpperCase() !== "LAUNCH"}
                data-testid="launch-confirm-fire"
                className="bg-deepred text-cream font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {busy ? "Sending…" : "Yes, send it"}
              </button>
              <button
                type="button"
                onClick={() => { setShowConfirm(false); setConfirmText(""); }}
                disabled={busy}
                data-testid="launch-confirm-cancel"
                className="font-sans text-xs uppercase tracking-wider text-muted-ink hover:text-ink"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Preview -------------------------------------------------------- */}
      <section data-testid="launch-preview-section">
        <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mb-3">Preview</p>
        <div className="border hairline rounded-sm overflow-hidden bg-white">
          <iframe
            title="Launch broadcast preview"
            srcDoc={preview.html}
            sandbox=""
            className="w-full h-[720px] block"
            data-testid="launch-preview-iframe"
          />
        </div>
      </section>
    </div>
  );
}
