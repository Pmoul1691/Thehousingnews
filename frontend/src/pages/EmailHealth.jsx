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

  useEffect(() => {
    if (loading) return;
    if (!user || !user.is_admin) { navigate("/feed", { replace: true }); return; }
    setTestEmail(user.email || "");
    api.get("/admin/email/dns-records").then((r) => setData(r.data)).catch(() => {}).finally(() => setFetching(false));
  }, [user, loading, navigate]);

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
