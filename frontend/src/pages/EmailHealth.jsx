import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

function Copy({ text }) {
  const onCopy = () => navigator.clipboard.writeText(text).then(
    () => toast.success("Copied"), () => toast.error("Could not copy")
  );
  return (
    <button onClick={onCopy} className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity px-2">
      Copy
    </button>
  );
}

export default function EmailHealth() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [fetching, setFetching] = useState(true);
  const [testEmail, setTestEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [readiness, setReadiness] = useState(null);
  const [readyLoading, setReadyLoading] = useState(false);
  const [publicUrl, setPublicUrl] = useState("");
  const [publicUrlSource, setPublicUrlSource] = useState("");
  const [savingUrl, setSavingUrl] = useState(false);
  const [sendingDigest, setSendingDigest] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user || !user.is_admin) { navigate("/feed", { replace: true }); return; }
    setTestEmail(user.email || "");
    Promise.all([
      api.get("/admin/email/dns-records").then((r) => setData(r.data)).catch(() => {}),
      api.get("/admin/email/public-url").then((r) => { setPublicUrl(r.data.value || ""); setPublicUrlSource(r.data.source); }).catch(() => {}),
    ]).finally(() => setFetching(false));
  }, [user, loading, navigate]);

  const runReadiness = async () => {
    setReadyLoading(true);
    try {
      const r = await api.get("/admin/email/readiness");
      setReadiness(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Readiness check failed");
    } finally { setReadyLoading(false); }
  };

  const savePublicUrl = async () => {
    const v = publicUrl.trim();
    if (!v) { toast.error("URL is required"); return; }
    setSavingUrl(true);
    try {
      await api.post("/admin/email/public-url", { url: v });
      setPublicUrlSource("db");
      toast.success("Saved. Emails will use this URL.");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(Array.isArray(d) ? d.map((x) => x?.msg).join("; ") : (d || "Save failed"));
    } finally { setSavingUrl(false); }
  };

  const sendDigestNow = async () => {
    if (!window.confirm("Send the Sunday brief to every admin right now?")) return;
    setSendingDigest(true);
    try {
      const r = await api.post("/admin/email/admin-digest/send");
      toast.success(`Sent to ${r.data.admins_emailed} admin${r.data.admins_emailed === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Digest send failed");
    } finally { setSendingDigest(false); }
  };

  const sendTest = async () => {
    if (!testEmail) return;
    setSending(true);
    try {
      await api.post("/admin/email/test-send", { to_email: testEmail });
      toast.success("Test email sent. Check the inbox and the headers.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Test send failed");
    } finally { setSending(false); }
  };

  return (
    <div className="container-wide py-12" data-testid="email-health-page">
      <div className="mb-3 flex items-center gap-2">
        <Link to="/admin" className="font-sans text-xs uppercase tracking-wider text-muted-ink hover:text-gold transition-colors">Admin</Link>
        <span className="font-sans text-xs text-muted-ink">.</span>
        <p className="font-sans text-xs uppercase tracking-wider text-gold font-semibold">Email health</p>
      </div>
      <h1 className="font-display font-semibold text-3xl ink mb-2">Deliverability.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed max-w-2xl mb-10">
        Add these DNS records at your registrar, then send a test email. SPF, DKIM, and DMARC must all pass before launching the public domain. Full runbook is at <code className="font-mono text-sm">/app/docs/email-setup.md</code>.
      </p>

      {fetching || !data ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : (
        <>
          <div className="grid sm:grid-cols-3 gap-4 mb-10" data-testid="email-health-summary">
            <div className="border hairline rounded-sm p-5 bg-cream">
              <p className="uppercase-label mb-2">Sender</p>
              <p className="font-display font-semibold text-base ink break-all">{data.sender_email}</p>
            </div>
            <div className="border hairline rounded-sm p-5 bg-cream">
              <p className="uppercase-label mb-2">Public domain</p>
              <p className="font-display font-semibold text-base ink break-all">{data.public_domain}</p>
            </div>
            <div className="border hairline rounded-sm p-5 bg-cream">
              <p className="uppercase-label mb-2">Brevo key</p>
              <p className={`font-display font-semibold text-base ${data.brevo_configured ? "text-gold" : "text-deepred"}`}>
                {data.brevo_configured ? "Configured" : "Missing"}
              </p>
            </div>
          </div>

          <section className="mb-12" data-testid="dns-records">
            <h2 className="font-display font-semibold text-xl ink mb-4">DNS records</h2>
            <div className="border hairline rounded-sm overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F5EDD6]">
                  <tr>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Purpose</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Name</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Type</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {data.records.map((r, idx) => (
                    <tr key={idx} data-testid={`dns-row-${idx}`} className="border-t hairline align-top">
                      <td className="p-3 font-display font-semibold text-sm ink whitespace-nowrap">{r.purpose}</td>
                      <td className="p-3 font-mono text-xs ink/80 break-all">{r.name}</td>
                      <td className="p-3 font-mono text-xs ink/80">{r.type}</td>
                      <td className="p-3 font-mono text-xs ink/90 break-all">
                        <div className="flex items-start gap-2">
                          <span className="flex-1">{r.value}</span>
                          <Copy text={r.value} />
                        </div>
                        {r.hint && <p className="font-serif text-xs text-muted-ink mt-2 italic">{r.hint}</p>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mb-12" data-testid="email-health-checklist">
            <h2 className="font-display font-semibold text-xl ink mb-4">Checklist</h2>
            <ol className="space-y-3 list-decimal pl-5">
              {data.checklist.map((c, idx) => (
                <li key={idx} className="prose-serif text-base ink/85 leading-relaxed">{c}</li>
              ))}
            </ol>
          </section>

          <section className="border hairline rounded-sm p-6 bg-cream mb-6" data-testid="email-health-public-url">
            <h2 className="font-display font-semibold text-xl ink mb-2">Public URL</h2>
            <p className="prose-serif text-sm ink/80 leading-relaxed max-w-prose mb-4">
              Where the digest and tracking links point. Save it here to flip the domain without a redeploy. Current source: <span className="font-sans font-semibold uppercase tracking-wider text-[11px] text-gold">{publicUrlSource || "unset"}</span>.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <input
                data-testid="public-url-input"
                value={publicUrl}
                onChange={(e) => setPublicUrl(e.target.value)}
                placeholder="https://ultradiannetwork.com"
                className="flex-1 min-w-[260px] bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
              />
              <button
                data-testid="public-url-save"
                onClick={savePublicUrl}
                disabled={savingUrl || !publicUrl.trim()}
                className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {savingUrl ? "Saving..." : "Save"}
              </button>
            </div>
          </section>

          <section className="border hairline rounded-sm p-6 bg-cream mb-6" data-testid="email-health-readiness">
            <div className="flex items-end justify-between mb-3 flex-wrap gap-3">
              <h2 className="font-display font-semibold text-xl ink">Launch readiness</h2>
              <button
                data-testid="readiness-run"
                onClick={runReadiness}
                disabled={readyLoading}
                className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity disabled:opacity-50"
              >
                {readyLoading ? "Checking..." : "Run readiness check"}
              </button>
            </div>
            {readiness ? (
              <>
                <div className={`inline-flex items-center gap-2 font-sans text-[11px] uppercase tracking-wider font-semibold px-2 py-1 rounded-sm border mb-4 ${readiness.ready ? "text-gold border-gold" : "text-deepred border-deepred"}`} data-testid="readiness-status">
                  {readiness.ready ? "Ready to launch" : "Not ready"}
                </div>
                <ul className="space-y-2">
                  {readiness.checks.map((c, idx) => (
                    <li key={idx} data-testid={`readiness-check-${idx}`} className="flex items-start gap-3">
                      <span className={`mt-0.5 inline-flex items-center justify-center w-5 h-5 rounded-full text-cream text-[11px] font-semibold ${c.ok ? "bg-gold" : "bg-deepred"}`}>
                        {c.ok ? "✓" : "✕"}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="font-display font-semibold text-sm ink">{c.name}</div>
                        <div className="font-mono text-xs text-muted-ink break-all">{c.detail}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="font-serif text-sm text-muted-ink italic">Click run to verify SPF, DKIM, DMARC, public URL reachability, and the Brevo key.</p>
            )}
          </section>

          <section className="border hairline rounded-sm p-6 bg-cream mb-6" data-testid="email-health-admin-digest">
            <div className="flex items-end justify-between mb-2 flex-wrap gap-3">
              <h2 className="font-display font-semibold text-xl ink">Sunday admin brief</h2>
              <button
                data-testid="admin-digest-send"
                onClick={sendDigestNow}
                disabled={sendingDigest}
                className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity disabled:opacity-50"
              >
                {sendingDigest ? "Sending..." : "Send to all admins now"}
              </button>
            </div>
            <p className="prose-serif text-sm ink/80 leading-relaxed max-w-prose">
              An engagement summary email goes to every admin every Sunday at 8am Chicago time. Use the button to fire it on demand for testing.
            </p>
          </section>

          <section className="border hairline rounded-sm p-6 bg-cream" data-testid="email-health-test">
            <h2 className="font-display font-semibold text-xl ink mb-2">Send a test email</h2>
            <p className="prose-serif text-sm ink/80 leading-relaxed max-w-prose mb-4">
              Goes through Brevo using the sender above. Open the result in Gmail and choose Show original to see SPF / DKIM / DMARC results.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <input
                data-testid="email-health-test-input"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="you@example.com"
                className="flex-1 min-w-[260px] bg-cream border hairline rounded-sm px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
              />
              <button
                data-testid="email-health-test-send"
                onClick={sendTest}
                disabled={sending || !testEmail || !data.brevo_configured}
                className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {sending ? "Sending..." : "Send test"}
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
