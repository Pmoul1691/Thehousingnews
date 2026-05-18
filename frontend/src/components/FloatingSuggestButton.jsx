import React, { useState } from "react";
import { useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

/**
 * Floating "Suggest an improvement" button shown on every screen.
 * Anyone (anon or signed-in) can submit. Anonymous submissions optionally
 * include an email. Signed-in submissions auto-attach the user.
 *
 * Positioned bottom-left so it never collides with the bottom-right Write button.
 */
export default function FloatingSuggestButton() {
  const { user } = useAuth();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [category, setCategory] = useState("idea");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (trimmed.length < 3) {
      toast.error("Add a little more detail first.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/improvements", {
        text: trimmed,
        category,
        page_path: loc.pathname,
        email: user ? null : (email.trim() || null),
      });
      toast.success("Thanks — sent to the editors.");
      setText("");
      setEmail("");
      setOpen(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not send. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="floating-suggest-btn"
        aria-label="Suggest an improvement"
        className="fixed bottom-6 left-6 z-40 inline-flex items-center gap-2 bg-ink text-cream font-sans font-semibold text-xs sm:text-sm px-3.5 sm:px-4 py-2 sm:py-2.5 rounded-full shadow-lg hover:opacity-90 hover:-translate-y-0.5 transition-all sm:bottom-8 sm:left-8 border border-gold/40"
      >
        <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 sm:w-4 sm:h-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
        </svg>
        <span className="hidden sm:inline">Suggest an improvement</span>
        <span className="sm:hidden">Suggest</span>
      </button>

      {open && (
        <div
          data-testid="suggest-modal"
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6"
          role="dialog"
          aria-modal="true"
        >
          <button
            aria-label="Close"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm cursor-default"
          />
          <form
            onSubmit={submit}
            className="relative w-full sm:max-w-lg bg-cream border hairline rounded-t-lg sm:rounded-sm shadow-2xl p-6 sm:p-8"
          >
            <div className="flex items-start justify-between mb-1">
              <p className="uppercase-label">Help us improve</p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                data-testid="suggest-close-btn"
                className="text-muted-ink hover:text-ink transition-colors -mt-2 -mr-2 p-2"
                aria-label="Close"
              >
                <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <h2 className="font-display font-semibold text-2xl ink mb-2">What would make this better?</h2>
            <p className="font-serif text-sm text-muted-ink leading-relaxed mb-5">
              Bug, feature request, copy nit, whatever. We read every one.
            </p>

            <div className="flex items-center gap-2 mb-4 flex-wrap">
              {["idea", "bug", "copy", "design", "other"].map((c) => (
                <button
                  key={c}
                  type="button"
                  data-testid={`suggest-cat-${c}`}
                  onClick={() => setCategory(c)}
                  className={`font-sans text-[11px] uppercase tracking-[0.18em] font-semibold px-3 py-1.5 rounded-full transition-colors ${
                    category === c
                      ? "bg-gold text-cream"
                      : "border hairline text-muted-ink hover:text-ink hover:border-gold/50"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>

            <textarea
              data-testid="suggest-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={2000}
              autoFocus
              placeholder="Be specific. A sentence is enough."
              className="w-full bg-white border hairline rounded-sm p-3 font-serif text-base ink leading-relaxed focus:outline-none focus:ring-1 focus:ring-gold min-h-[140px]"
            />
            <div className="text-right font-sans text-[10px] text-muted-ink mt-1">{text.length}/2000</div>

            {!user && (
              <div className="mt-3">
                <label className="block uppercase-label mb-2">Email (optional)</label>
                <input
                  data-testid="suggest-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-white border hairline rounded-sm p-2.5 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
                />
                <p className="font-sans text-[11px] text-muted-ink mt-1.5">If you want a reply.</p>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t hairline">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="font-sans font-medium text-sm text-muted-ink hover:text-ink transition-colors px-3 py-2"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting || text.trim().length < 3}
                data-testid="suggest-submit"
                className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
