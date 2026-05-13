import React from "react";
import { toast } from "sonner";

const ICON = "inline-block w-4 h-4";

// Each share target is either an explicit `intent` URL (opens in new tab) or
// a `copy: true` flag meaning we copy the link to the clipboard and toast a
// hint - used for apps that have no public share URL on the web (Instagram,
// TikTok, YouTube).
function buildTargets({ url, text, hasVideo }) {
  const u = encodeURIComponent(url);
  const t = encodeURIComponent(text || "");
  const base = [
    {
      key: "linkedin",
      label: "LinkedIn",
      testId: "share-linkedin",
      intent: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
      icon: (
        <svg viewBox="0 0 24 24" className={ICON} fill="currentColor" aria-hidden="true">
          <path d="M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zM8.5 18.5h-3v-9h3v9zm-1.5-10.3a1.75 1.75 0 1 1 0-3.5 1.75 1.75 0 0 1 0 3.5zM18.5 18.5h-3v-4.7c0-1.1 0-2.5-1.5-2.5s-1.7 1.2-1.7 2.4v4.8h-3v-9h2.9v1.2h.1c.4-.7 1.4-1.5 2.9-1.5 3.1 0 3.7 2 3.7 4.7v4.6z" />
        </svg>
      ),
    },
    {
      key: "x",
      label: "X",
      testId: "share-x",
      intent: `https://twitter.com/intent/tweet?url=${u}&text=${t}`,
      icon: (
        <svg viewBox="0 0 24 24" className={ICON} fill="currentColor" aria-hidden="true">
          <path d="M17.5 3H21l-7.4 8.5L22 21h-6.7l-5-6.6L4.5 21H1l8-9.1L1.5 3h6.8l4.5 6 4.7-6zm-1.2 16.2h2L7.8 4.7H5.7l10.6 14.5z" />
        </svg>
      ),
    },
    {
      key: "facebook",
      label: "Facebook",
      testId: "share-facebook",
      intent: `https://www.facebook.com/sharer/sharer.php?u=${u}`,
      icon: (
        <svg viewBox="0 0 24 24" className={ICON} fill="currentColor" aria-hidden="true">
          <path d="M13.5 22v-8h2.7l.4-3.2h-3.1V8.7c0-.9.3-1.6 1.7-1.6h1.6V4.2c-.3 0-1.3-.2-2.4-.2-2.4 0-4 1.5-4 4.1v2.7H7.6V14h2.8v8h3.1z" />
        </svg>
      ),
    },
    {
      key: "substack",
      label: "Substack",
      testId: "share-substack",
      intent: `https://substack.com/note/quote?url=${u}`,
      icon: (
        <svg viewBox="0 0 24 24" className={ICON} fill="currentColor" aria-hidden="true">
          <path d="M4 4h16v3H4V4zm0 5.5h16v3H4v-3zM4 15h16v6l-8-4-8 4v-6z" />
        </svg>
      ),
    },
    {
      key: "instagram",
      label: "Instagram",
      testId: "share-instagram",
      copy: true,
      hint: "Link copied. Paste it into Instagram.",
      icon: (
        <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="5" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
        </svg>
      ),
    },
    {
      key: "tiktok",
      label: "TikTok",
      testId: "share-tiktok",
      copy: true,
      hint: "Link copied. Paste it into TikTok.",
      icon: (
        <svg viewBox="0 0 24 24" className={ICON} fill="currentColor" aria-hidden="true">
          <path d="M14 3v10.1a3.1 3.1 0 1 1-3.1-3.1v3a.1.1 0 0 0 0 .1A.1.1 0 1 0 11 13V3h3zm3.9 3.9a4.6 4.6 0 0 1-2.6-2.4H17a4.8 4.8 0 0 0 4.9 4.7v3a7.8 7.8 0 0 1-4-1.1V13a6.1 6.1 0 1 1-6.1-6.1c.3 0 .6 0 .9.1v3.1a3.1 3.1 0 1 0 2.2 3v-6.2h3z" />
        </svg>
      ),
    },
  ];
  base.push({
    key: "youtube",
    label: hasVideo ? "YouTube" : "YouTube",
    testId: "share-youtube",
    copy: true,
    hint: hasVideo
      ? "Link copied. Paste it in your YouTube description."
      : "Link copied. Paste it on YouTube.",
    icon: (
      <svg viewBox="0 0 24 24" className={ICON} fill="currentColor" aria-hidden="true">
        <path d="M22 7.3a3 3 0 0 0-2.1-2.1C18 4.8 12 4.8 12 4.8s-6 0-7.9.4A3 3 0 0 0 2 7.3 31 31 0 0 0 1.6 12 31 31 0 0 0 2 16.7a3 3 0 0 0 2.1 2.1c1.9.4 7.9.4 7.9.4s6 0 7.9-.4A3 3 0 0 0 22 16.7 31 31 0 0 0 22.4 12 31 31 0 0 0 22 7.3zM10 15V9l5.2 3-5.2 3z" />
      </svg>
    ),
  });
  base.push({
    key: "copy",
    label: "Copy link",
    testId: "share-copy",
    copy: true,
    hint: "Link copied.",
    icon: (
      <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <rect x="9" y="9" width="11" height="11" rx="2" />
        <path d="M5 15V6a2 2 0 0 1 2-2h9" />
      </svg>
    ),
  });
  return base;
}

async function copyLink(url, hint) {
  try {
    await navigator.clipboard.writeText(url);
    toast.success(hint || "Link copied.");
  } catch (_e) {
    toast.error("Could not copy. Long-press the URL to copy manually.");
  }
}

export default function ShareButtons({ url, title, hasVideo = false, dense = false }) {
  const shareUrl = url || (typeof window !== "undefined" ? window.location.href : "");
  const targets = buildTargets({ url: shareUrl, text: title, hasVideo });

  return (
    <div data-testid="share-buttons" className={dense ? "flex flex-wrap gap-2" : "flex flex-wrap gap-3 items-center"}>
      <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-ink mr-1">Share</span>
      {targets.map((t) => {
        const className =
          "inline-flex items-center gap-1.5 border hairline rounded-sm px-2.5 py-1.5 font-sans text-xs font-medium ink hover:border-gold hover:text-gold transition-colors";
        if (t.copy) {
          return (
            <button
              key={t.key}
              type="button"
              data-testid={t.testId}
              onClick={() => copyLink(shareUrl, t.hint)}
              className={className}
              aria-label={`Share to ${t.label}`}
            >
              {t.icon}
              <span>{t.label}</span>
            </button>
          );
        }
        return (
          <a
            key={t.key}
            href={t.intent}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={t.testId}
            className={className}
            aria-label={`Share to ${t.label}`}
          >
            {t.icon}
            <span>{t.label}</span>
          </a>
        );
      })}
    </div>
  );
}
