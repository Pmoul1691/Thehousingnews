import React, { useState } from "react";
import api from "@/lib/api";

/**
 * Newsletter signup band shown periodically in the river and on /newsletter.
 * Goes to Brevo's "The Housing News Daily" list (set name via env var
 * AGG_NEWSLETTER_LIST_NAME server-side). Locally captured first, then pushed.
 */
export default function NewsletterBand({ compact = false }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | submitting | ok | error
  const [errorMsg, setErrorMsg] = useState("");

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setState("submitting");
    try {
      await api.post("/newsletter/subscribe", {
        email: email.trim(),
        source: window.location.pathname,
      });
      setState("ok");
    } catch (e2) {
      setErrorMsg(e2?.response?.data?.detail || "Could not subscribe. Try again.");
      setState("error");
    }
  };

  return (
    <div
      className={`my-${compact ? "4" : "8"} bg-agg-navy text-agg-cream px-5 py-${compact ? "4" : "6"} rounded-sm`}
      data-testid="agg-newsletter-band"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <p className="font-display font-semibold text-base sm:text-lg leading-tight">
            The Housing News, in your inbox.
          </p>
          <p className="text-sm text-agg-cream/75 mt-1">
            One quiet email a day. The headlines that matter. No spam.
          </p>
        </div>
        {state === "ok" ? (
          <p data-testid="agg-newsletter-success" className="font-sans text-sm text-agg-orange">
            Check your inbox for a confirmation link.
          </p>
        ) : (
          <form onSubmit={onSubmit} className="flex gap-2 shrink-0">
            <input
              type="email"
              required
              autoComplete="email"
              data-testid="agg-newsletter-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@yourbrokerage.com"
              className="w-full sm:w-64 bg-agg-navy-deep border border-agg-navy-deep text-agg-cream placeholder:text-agg-cream/50 px-3 py-2 rounded-sm text-sm focus:outline-none focus:ring-1 focus:ring-agg-orange"
            />
            <button
              type="submit"
              disabled={state === "submitting"}
              data-testid="agg-newsletter-submit"
              className="bg-agg-orange text-agg-navy font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {state === "submitting" ? "..." : "Subscribe"}
            </button>
          </form>
        )}
      </div>
      {state === "error" && (
        <p className="mt-3 text-sm text-agg-orange/90" data-testid="agg-newsletter-error">{errorMsg}</p>
      )}
    </div>
  );
}
