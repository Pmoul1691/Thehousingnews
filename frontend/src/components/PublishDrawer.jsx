import React, { useEffect } from "react";
import RegionPicker from "@/components/RegionPicker";

/**
 * Right-side slide-in drawer that holds all publish settings: schedule,
 * audience, regions, attachment summary, and the final action button.
 *
 * State is owned by `Composer.jsx` (the editor) — this component is a
 * controlled view. Closing the drawer just hides it; nothing in the post
 * is committed until the user clicks the primary CTA.
 */
export default function PublishDrawer({
  open,
  onClose,
  mode,                    // "post" | "essay"
  scheduledAt,
  setScheduledAt,
  releaseLabel,            // e.g. "5:30pm CT"
  mediaSummary,            // {images, video, audio, embed} counts/strings
  regions,
  setRegions,
  currentPrompt,
  linkPrompt,
  setLinkPrompt,
  onPublish,
  posting,
  canPublish,
  publishLabel,
}) {
  // Lock body scroll while open so the cream background doesn't peek through.
  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  const isEssay = mode === "essay";
  const scheduleHuman = scheduledAt
    ? new Date(scheduledAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
    : null;

  return (
    <>
      {/* Overlay */}
      <div
        data-testid="publish-drawer-overlay"
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-[#1D2D44]/40 backdrop-blur-sm transition-opacity duration-300 ${open ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        aria-hidden={!open}
      />
      {/* Drawer */}
      <aside
        data-testid="publish-settings-drawer"
        role="dialog"
        aria-label="Publish settings"
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        className={`fixed inset-y-0 right-0 z-50 w-full max-w-md bg-cream border-l border-gold/20 shadow-2xl flex flex-col transform transition-transform duration-300 ease-out ${open ? "translate-x-0" : "translate-x-full pointer-events-none"}`}
      >
        {/* Header */}
        <header className="flex items-center justify-between p-6 border-b border-gold/10">
          <div>
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-gold">
              Publish settings
            </p>
            <h2 className="font-display font-semibold text-2xl ink mt-1">
              {isEssay ? "Ready to send?" : "Queue this post?"}
            </h2>
          </div>
          <button
            type="button"
            data-testid="publish-drawer-close"
            onClick={onClose}
            className="text-muted-ink hover:text-ink transition-colors p-2 -m-2"
            aria-label="Close publish settings"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8">
          {/* Schedule */}
          <section>
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">
              Schedule
            </p>
            {isEssay ? (
              <div className="space-y-3" data-testid="drawer-schedule-section">
                <label className="block">
                  <span className="font-sans text-xs text-muted-ink">Send at</span>
                  <input
                    type="datetime-local"
                    data-testid="drawer-schedule-input"
                    value={scheduledAt}
                    onChange={(e) => setScheduledAt(e.target.value)}
                    className="mt-1 w-full bg-white border border-gold/20 rounded-md px-3 py-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
                  />
                </label>
                <p className="font-sans text-xs text-muted-ink leading-relaxed">
                  Leave empty to publish now. Scheduled essays email your followers at the chosen time.
                  {scheduledAt && (
                    <>
                      {" "}<button
                        type="button"
                        data-testid="drawer-schedule-clear"
                        onClick={() => setScheduledAt("")}
                        className="underline text-gold hover:opacity-80 transition-opacity"
                      >
                        Clear
                      </button>
                    </>
                  )}
                </p>
              </div>
            ) : (
              <div className="bg-white p-4 rounded-md border border-gold/20" data-testid="drawer-next-drop">
                <p className="font-sans text-xs text-muted-ink">Next daily drop</p>
                <p className="font-display font-semibold text-lg ink mt-1">{releaseLabel || "Soon"}</p>
                <p className="font-sans text-xs text-muted-ink mt-2 leading-relaxed">
                  Short posts release together at 8:30 AM and 5:30 PM CT so the room reads them as one issue.
                </p>
              </div>
            )}
          </section>

          {/* Audience */}
          <section>
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">
              Audience
            </p>
            <div className="bg-white p-4 rounded-md border border-gold/20" data-testid="drawer-audience">
              <p className="font-display font-semibold text-base ink">Everyone</p>
              <p className="font-sans text-xs text-muted-ink mt-1 leading-relaxed">
                {isEssay
                  ? "Goes out to all your followers by email and appears on the magazine."
                  : "Released to the full network in the next daily drop."}
              </p>
            </div>
          </section>

          {/* Regions */}
          <section data-testid="drawer-regions-section">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">
              Regions
            </p>
            <RegionPicker
              controlled
              value={regions}
              onChange={setRegions}
              emptyLabel="Leave empty and Claude will auto-tag from the content."
              testidPrefix="drawer-region"
            />
          </section>

          {/* Weekly prompt link */}
          {currentPrompt && (
            <section>
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">
                This week's subject
              </p>
              <label className="flex items-start gap-3 bg-white p-4 rounded-md border border-gold/20 cursor-pointer" data-testid="drawer-prompt-link">
                <input
                  type="checkbox"
                  checked={linkPrompt}
                  onChange={(e) => setLinkPrompt(e.target.checked)}
                  data-testid="drawer-prompt-link-checkbox"
                  className="mt-1 accent-gold cursor-pointer"
                />
                <span>
                  <span className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold">Link this post</span>
                  <span className="block font-display font-semibold text-sm ink leading-snug mt-1">{currentPrompt.title}</span>
                </span>
              </label>
            </section>
          )}

          {/* Attachments summary */}
          <section data-testid="drawer-attachments-summary">
            <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-3">
              Attachments
            </p>
            <ul className="bg-white p-4 rounded-md border border-gold/20 space-y-2 font-sans text-sm ink">
              <li>
                <span className="text-muted-ink">Images:</span>{" "}
                <span className="font-semibold">{mediaSummary.images}</span>
                {mediaSummary.images === 0 && <span className="text-muted-ink text-xs"> (max 4, up to 6 MB each)</span>}
              </li>
              <li>
                <span className="text-muted-ink">Video:</span>{" "}
                <span className="font-semibold">{mediaSummary.video || "none"}</span>
              </li>
              <li>
                <span className="text-muted-ink">Audio:</span>{" "}
                <span className="font-semibold">{mediaSummary.audio || "none"}</span>
              </li>
              <li>
                <span className="text-muted-ink">External embed:</span>{" "}
                <span className="font-semibold">{mediaSummary.embed || "none"}</span>
              </li>
            </ul>
            <p className="font-sans text-[11px] text-muted-ink mt-2 leading-relaxed">
              Attach more from the editor row beneath the writing area.
            </p>
          </section>
        </div>

        {/* Footer */}
        <footer className="p-6 border-t border-gold/10 bg-cream">
          {scheduleHuman && isEssay && (
            <p className="font-sans text-xs text-muted-ink mb-3" data-testid="drawer-schedule-preview">
              Will publish <span className="font-semibold ink">{scheduleHuman}</span>
            </p>
          )}
          <button
            type="button"
            data-testid="drawer-final-publish-button"
            onClick={onPublish}
            disabled={!canPublish || posting}
            className="w-full py-3 bg-gold hover:bg-[#967534] disabled:opacity-50 disabled:cursor-not-allowed text-cream rounded-full font-sans font-semibold text-sm transition-colors"
          >
            {publishLabel}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="w-full mt-2 py-2 text-muted-ink hover:text-ink font-sans text-sm transition-colors"
          >
            Back to editor
          </button>
        </footer>
      </aside>
    </>
  );
}
