import React from "react";

// Lightweight content placeholder for the main feed stream. Renders three
// shimmering post-shaped blocks so the page has structure while data loads,
// instead of a blank "Loading." line. Pure CSS animation, no JS.
export function PostSkeleton({ count = 3 }) {
  return (
    <div data-testid="post-skeleton-list" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="border-b hairline py-6 animate-pulse"
          data-testid={`post-skeleton-${i}`}
        >
          {/* Author row */}
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-full bg-[#E8D4A0]/40" />
            <div className="flex-1">
              <div className="h-3 w-32 bg-[#E8D4A0]/40 rounded-sm mb-2" />
              <div className="h-2 w-20 bg-[#E8D4A0]/30 rounded-sm" />
            </div>
          </div>
          {/* Title */}
          <div className="h-4 w-3/4 bg-[#E8D4A0]/50 rounded-sm mb-3" />
          {/* Body lines */}
          <div className="space-y-2">
            <div className="h-3 w-full bg-[#E8D4A0]/30 rounded-sm" />
            <div className="h-3 w-11/12 bg-[#E8D4A0]/30 rounded-sm" />
            <div className="h-3 w-2/3 bg-[#E8D4A0]/30 rounded-sm" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Compact skeleton for The Daily news cards. Matches DailyCard's dimensions
// so the layout doesn't shift when real content arrives.
export function NewsCardSkeleton({ count = 6 }) {
  return (
    <div
      data-testid="news-card-skeleton-list"
      aria-hidden="true"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="border border-slate-200 rounded-sm bg-white p-5 animate-pulse"
          data-testid={`news-card-skeleton-${i}`}
        >
          {/* Publisher header */}
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-sm bg-slate-200" />
            <div className="flex-1">
              <div className="h-3 w-28 bg-slate-200 rounded-sm mb-2" />
              <div className="h-2 w-16 bg-slate-100 rounded-sm" />
            </div>
          </div>
          {/* Headline */}
          <div className="h-4 w-full bg-slate-200 rounded-sm mb-2" />
          <div className="h-4 w-4/5 bg-slate-200 rounded-sm mb-4" />
          {/* Snippet */}
          <div className="space-y-2">
            <div className="h-3 w-full bg-slate-100 rounded-sm" />
            <div className="h-3 w-11/12 bg-slate-100 rounded-sm" />
            <div className="h-3 w-3/4 bg-slate-100 rounded-sm" />
          </div>
        </div>
      ))}
    </div>
  );
}
