import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import PageMeta from "@/components/PageMeta";

/**
 * /subscribe — Public landing page for the free Daily Brief opt-in.
 *
 * Anyone can subscribe; no application, no approval. Backend uses double
 * opt-in via /api/newsletter/subscribe → confirmation email → confirm link.
 *
 * Three signals shown to reduce form anxiety before submit:
 *   1. What you get — explicit "twice daily, free forever"
 *   2. Live reader count from /api/newsletter/status (soft proof)
 *   3. One-click unsubscribe in every email (calming the spam concern)
 */
export default function Subscribe() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | submitting | ok | error | already
  const [errorMsg, setErrorMsg] = useState("");
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/newsletter/status").then((r) => setStats(r.data)).catch(() => setStats(null));
  }, []);

  const onSubmit = async (e) => {
    e.preventDefault();
    const value = email.trim().toLowerCase();
    if (!value) return;
    setState("submitting");
    try {
      const r = await api.post("/newsletter/subscribe", { email: value, source: "subscribe_page" });
      if (r.data.already_member || r.data.already_confirmed) {
        setState("already");
      } else {
        setState("ok");
      }
    } catch (e2) {
      setErrorMsg(e2?.response?.data?.detail || "Could not subscribe. Try again.");
      setState("error");
    }
  };

  return (
    <div className="bg-cream min-h-screen" data-testid="subscribe-page">
      <PageMeta
        title="Subscribe to The Daily · The Housing News"
        description="A twice-daily curated brief on the residential real-estate industry. Free forever."
      />

      <div className="container-narrow py-16 sm:py-24">
        <header className="text-center mb-12">
          <p className="uppercase-label mb-3">The Daily</p>
          <h1 className="font-display font-semibold text-4xl sm:text-5xl lg:text-6xl ink leading-[1.05] mb-5">
            The housing news,<br />curated.
          </h1>
          <p className="prose-serif text-base sm:text-lg ink/80 leading-relaxed max-w-xl mx-auto">
            One quiet brief in the morning, one in the evening. Eight stories the industry is actually talking about, plus a podcast we listened to. Free forever for everyone in housing.
          </p>
        </header>

        {/* Subscribe form ----------------------------------------------- */}
        <section className="border-y hairline py-10 mb-12">
          {state === "ok" && (
            <div className="text-center" data-testid="subscribe-success">
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-2">Almost in</p>
              <h2 className="font-display font-semibold text-2xl ink mb-3">Check your inbox.</h2>
              <p className="prose-serif text-base ink/80 max-w-md mx-auto">
                We sent a confirmation link to <strong className="ink">{email}</strong>. Click it and you&apos;re subscribed — no further steps.
              </p>
            </div>
          )}

          {state === "already" && (
            <div className="text-center" data-testid="subscribe-already">
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-2">Already in</p>
              <h2 className="font-display font-semibold text-2xl ink mb-3">You&apos;re already subscribed.</h2>
              <p className="prose-serif text-base ink/80">No action needed — keep an eye out for the next brief.</p>
            </div>
          )}

          {(state === "idle" || state === "submitting" || state === "error") && (
            <form onSubmit={onSubmit} className="max-w-md mx-auto" data-testid="subscribe-form">
              <label htmlFor="subscribe-email" className="block font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-muted-ink mb-2">
                Your email
              </label>
              <div className="flex gap-2 flex-col sm:flex-row">
                <input
                  id="subscribe-email"
                  data-testid="subscribe-email-input"
                  type="email"
                  required
                  autoComplete="email"
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@yourbrokerage.com"
                  className="flex-1 border hairline bg-white rounded-sm px-4 py-3 font-sans text-base focus:outline-none focus:border-gold"
                />
                <button
                  type="submit"
                  disabled={state === "submitting"}
                  data-testid="subscribe-submit"
                  className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50 whitespace-nowrap"
                >
                  {state === "submitting" ? "Sending…" : "Send me the brief"}
                </button>
              </div>
              {state === "error" && (
                <p className="mt-3 font-serif text-sm text-deepred" data-testid="subscribe-error">{errorMsg}</p>
              )}
              <p className="mt-4 font-serif italic text-xs text-muted-ink text-center">
                One-click unsubscribe at the bottom of every email.
              </p>
            </form>
          )}
        </section>

        {/* What you get ------------------------------------------------ */}
        <section className="grid sm:grid-cols-3 gap-8 mb-12">
          <Detail eyebrow="Morning" title="7:30 AM CT" body="Eight stories the housing industry will be talking about that day, plus a podcast pick." />
          <Detail eyebrow="Evening" title="5:30 PM CT" body="The day's most-discussed stories, plus the trending tags on the network." />
          <Detail eyebrow="Always" title="Free" body="No paywalls, no premium tier, no upsell. The Daily is free forever for everyone in housing." />
        </section>

        {/* Social proof ------------------------------------------------ */}
        {stats && stats.total_readers > 0 && (
          <p className="text-center font-serif italic text-base text-muted-ink mb-12" data-testid="subscribe-social-proof">
            Joined by {stats.total_readers} real-estate professional{stats.total_readers === 1 ? "" : "s"} reading The Daily.
          </p>
        )}

        {/* Want to write too? ----------------------------------------- */}
        <div className="border hairline rounded-sm bg-cream p-6 text-center">
          <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-2">
            Want to write too?
          </p>
          <p className="font-serif text-base ink/85 mb-4">
            The Housing News also publishes essays from working real-estate professionals. Reading is open; writing is by invitation.
          </p>
          <Link
            to="/join"
            data-testid="subscribe-apply-link"
            className="font-sans text-xs uppercase tracking-[0.18em] font-semibold text-gold hover:text-ink transition-colors"
          >
            Join to write &rarr;
          </Link>
        </div>
      </div>
    </div>
  );
}

function Detail({ eyebrow, title, body }) {
  return (
    <div>
      <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold mb-1">{eyebrow}</p>
      <p className="font-display font-semibold text-xl ink mb-2">{title}</p>
      <p className="font-serif text-sm ink/80 leading-relaxed">{body}</p>
    </div>
  );
}
