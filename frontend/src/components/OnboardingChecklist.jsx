import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * "Getting started" sticky checklist on /feed.
 * Substack-style — auto-marks items as done from server state where possible
 * (email_verified, has_profile, regions, has any post). The "read first essay"
 * item is tracked client-side via localStorage since it's a soft heuristic.
 *
 * The whole component is dismissible. Once all items are checked OR the user
 * dismisses, it never re-renders unless they reset onboarding from Settings.
 */
const LS_DISMISSED = "thn_onboarding_dismissed_v1";
const LS_READ_ESSAY = "thn_onboarding_read_essay_v1";

export default function OnboardingChecklist() {
  const { user } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [readEssay, setReadEssay] = useState(false);
  const [regions, setRegions] = useState(null);
  const [hasPost, setHasPost] = useState(null);

  useEffect(() => {
    setReadEssay(localStorage.getItem(LS_READ_ESSAY) === "1");
  }, []);

  useEffect(() => {
    let alive = true;
    if (!user || user.status !== "approved") return undefined;
    api.get("/users/me/regions").then((r) => { if (alive) setRegions(r.data?.regions || []); }).catch(() => {});
    api.get("/posts/mine").then((r) => { if (alive) setHasPost((r.data?.items || []).length > 0); }).catch(() => setHasPost(false));
    return () => { alive = false; };
  }, [user]);

  const steps = useMemo(() => {
    if (!user) return [];
    return [
      {
        key: "verify",
        label: "Verify your email",
        done: !!user.email_verified,
        cta: { text: "Resend", to: "#verify" },
      },
      {
        key: "profile",
        label: "Complete your profile",
        done: !!user.has_profile,
        cta: { text: "Open settings", to: "/settings" },
      },
      {
        key: "regions",
        label: "Pick your regions (or skip — see everything)",
        done: regions !== null,  // visiting the regions tab implicitly is fine; default is "see all"
        cta: { text: "Pick regions", to: "/settings#regions" },
        optional: true,
      },
      {
        key: "read",
        label: "Read your first essay",
        done: readEssay,
        cta: { text: "Browse essays", to: "/essays" },
      },
      {
        key: "write",
        label: "Write your first take",
        done: hasPost === true,
        cta: { text: "Open the editor", to: "/write" },
      },
    ];
  }, [user, regions, readEssay, hasPost]);

  const completed = steps.filter((s) => s.done).length;
  const total = steps.length;
  const allDone = completed === total;

  // Only show for approved members who haven't dismissed or finished.
  const dismissed = typeof window !== "undefined" && localStorage.getItem(LS_DISMISSED) === "1";
  if (!user || user.status !== "approved" || dismissed || allDone) return null;

  const dismiss = () => {
    localStorage.setItem(LS_DISMISSED, "1");
    setCollapsed(true);
    // Force a re-render via the state we already have; the early return on the
    // next mount will hide the component entirely.
    window.dispatchEvent(new Event("storage"));
  };

  return (
    <aside
      data-testid="onboarding-checklist"
      className="mb-6 border border-gold/40 bg-cream-soft rounded-sm overflow-hidden"
    >
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        data-testid="onboarding-toggle"
        className="w-full flex items-center justify-between gap-3 px-4 sm:px-5 py-3 hover:bg-gold/5 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold shrink-0">
            Getting started
          </span>
          <span className="font-mono text-xs text-muted-ink shrink-0">
            {completed} / {total}
          </span>
          <span className="hidden sm:inline font-serif text-sm text-muted-ink truncate">
            {steps.find((s) => !s.done)?.label || "All done."}
          </span>
        </div>
        <svg viewBox="0 0 24 24" className={`w-4 h-4 text-muted-ink transition-transform ${collapsed ? "" : "rotate-180"}`} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {!collapsed && (
        <div className="border-t border-gold/20 px-4 sm:px-5 py-4 space-y-3">
          {steps.map((s) => (
            <div
              key={s.key}
              data-testid={`onboarding-step-${s.key}`}
              className="flex items-center justify-between gap-3 flex-wrap"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span
                  aria-hidden="true"
                  className={`inline-flex items-center justify-center w-5 h-5 rounded-full shrink-0 ${
                    s.done ? "bg-gold text-cream" : "border hairline text-muted-ink"
                  }`}
                >
                  {s.done ? (
                    <svg viewBox="0 0 24 24" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  ) : (
                    <span className="block w-1.5 h-1.5 rounded-full bg-muted-ink/40" />
                  )}
                </span>
                <span className={`font-serif text-sm leading-snug ${s.done ? "text-muted-ink line-through" : "ink/90"}`}>
                  {s.label}
                </span>
              </div>
              {!s.done && s.cta?.to?.startsWith("/") && (
                <Link
                  to={s.cta.to}
                  data-testid={`onboarding-cta-${s.key}`}
                  className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity shrink-0"
                >
                  {s.cta.text} →
                </Link>
              )}
            </div>
          ))}

          <div className="flex items-center justify-end pt-2 border-t border-gold/15">
            <button
              type="button"
              onClick={dismiss}
              data-testid="onboarding-dismiss"
              className="font-sans text-[11px] uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors"
            >
              Hide this
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}

// Helper to mark the "read first essay" step done. Call from EssayDetail.jsx.
export function markEssayReadOnce() {
  try { localStorage.setItem(LS_READ_ESSAY, "1"); } catch (_e) { /* silent */ }
}

// Settings can reset onboarding via this helper.
export function resetOnboarding() {
  try {
    localStorage.removeItem(LS_DISMISSED);
    localStorage.removeItem(LS_READ_ESSAY);
  } catch (_e) { /* silent */ }
}
