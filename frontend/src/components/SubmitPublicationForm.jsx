import React, { useState } from "react";
import api from "@/lib/api";

/**
 * Public form on /about — visitors can recommend a publication for the
 * aggregator. Captured into agg_publisher_suggestions and reviewed in
 * /admin/aggregator. Rate-limited server-side: 5 / IP / hour.
 */
export default function SubmitPublicationForm() {
  const [form, setForm] = useState({
    email: "",
    publication_name: "",
    feed_url: "",
    homepage_url: "",
    reason: "",
  });
  const [state, setState] = useState("idle"); // idle | submitting | ok | error
  const [error, setError] = useState("");

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.email.trim() || !form.publication_name.trim() || !form.feed_url.trim()) {
      setError("Email, name, and feed URL are required.");
      return;
    }
    setState("submitting");
    try {
      await api.post("/agg/publisher-suggestions", {
        email: form.email.trim(),
        publication_name: form.publication_name.trim(),
        feed_url: form.feed_url.trim(),
        homepage_url: form.homepage_url.trim() || undefined,
        reason: form.reason.trim() || undefined,
      });
      setState("ok");
    } catch (e2) {
      setError(e2?.response?.data?.detail || "Could not submit. Try again.");
      setState("error");
    }
  };

  if (state === "ok") {
    return (
      <div
        data-testid="submit-pub-success"
        className="border-l-2 border-agg-orange pl-5 py-4 bg-slate-50 rounded-sm"
      >
        <p className="font-display font-semibold text-lg text-agg-navy mb-1">Got it. Thank you.</p>
        <p className="font-serif text-sm text-slate-700">
          We will review the feed and add it if it fits. We answer every submission, even when the answer is no.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="border border-slate-200 rounded-sm p-5 sm:p-6 bg-slate-50"
      data-testid="submit-pub-form"
    >
      <p className="font-sans text-[11px] uppercase tracking-[0.22em] font-semibold text-agg-orange mb-2">
        Suggest a publication
      </p>
      <p className="font-serif text-sm text-slate-700 mb-5 leading-relaxed">
        We are adding to the roster every week. If you publish residential real estate content,
        or read a feed we are missing, tell us. We answer every note.
      </p>

      <div className="grid sm:grid-cols-2 gap-3 mb-3">
        <input
          required
          type="email"
          autoComplete="email"
          data-testid="submit-pub-email"
          value={form.email}
          onChange={(e) => setField("email", e.target.value)}
          placeholder="Your email"
          className="bg-white border border-slate-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-agg-orange"
        />
        <input
          required
          data-testid="submit-pub-name"
          value={form.publication_name}
          onChange={(e) => setField("publication_name", e.target.value)}
          placeholder="Publication name"
          className="bg-white border border-slate-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-agg-orange"
        />
      </div>
      <input
        required
        type="url"
        data-testid="submit-pub-feed"
        value={form.feed_url}
        onChange={(e) => setField("feed_url", e.target.value)}
        placeholder="RSS feed URL (https://...)"
        className="w-full bg-white border border-slate-200 rounded-sm px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-agg-orange"
      />
      <input
        type="url"
        data-testid="submit-pub-homepage"
        value={form.homepage_url}
        onChange={(e) => setField("homepage_url", e.target.value)}
        placeholder="Homepage URL (optional)"
        className="w-full bg-white border border-slate-200 rounded-sm px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-agg-orange"
      />
      <textarea
        rows={3}
        data-testid="submit-pub-reason"
        value={form.reason}
        onChange={(e) => setField("reason", e.target.value)}
        placeholder="A sentence on why this belongs here (optional)"
        className="w-full bg-white border border-slate-200 rounded-sm px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-1 focus:ring-agg-orange resize-none"
      />

      {error && (
        <p data-testid="submit-pub-error" className="text-sm text-red-700 mb-3">{error}</p>
      )}

      <button
        type="submit"
        disabled={state === "submitting"}
        data-testid="submit-pub-submit"
        className="bg-agg-orange text-agg-navy font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
      >
        {state === "submitting" ? "Sending..." : "Submit"}
      </button>
    </form>
  );
}
