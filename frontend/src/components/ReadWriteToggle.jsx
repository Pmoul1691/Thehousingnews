import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

/**
 * Bottom-right contextual floating button that lets a signed-in member flip
 * between the two main surfaces: read (the daily news aggregator at /news)
 * and write (the member feed at /feed). Renders nothing on any other route
 * or for signed-out visitors.
 *
 * Replaces the FloatingWriteButton's slot on /news and /feed (it auto-hides
 * on those routes) so we never have two pills stacking in the same corner.
 */
export default function ReadWriteToggle() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const inNews = pathname === "/news" || pathname.startsWith("/news/");
  const inFeed = pathname === "/feed" || pathname.startsWith("/feed/");
  if (!inNews && !inFeed) return null;
  // Show only for signed-in members. Visitors on /news see no toggle.
  if (!user || user.status !== "approved") return null;

  const goingToWrite = inNews;
  const target = goingToWrite ? "/feed" : "/news";
  const label = goingToWrite ? "Write a post" : "Read The Daily";
  const testid = goingToWrite ? "rw-toggle-write" : "rw-toggle-read";

  const icon = goingToWrite ? (
    // Quill / pencil icon for "write"
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19l7-7 3 3-7 7-3-3z" />
      <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z" />
      <path d="M2 2l7.586 7.586" />
      <circle cx="11" cy="11" r="2" />
    </svg>
  ) : (
    // Newspaper icon for "read"
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 22V4a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v18l-3-2-3 2-3-2-3 2-3-2z" />
      <path d="M8 6h7" />
      <path d="M8 10h7" />
      <path d="M8 14h4" />
    </svg>
  );

  return (
    <Link
      to={target}
      data-testid={testid}
      aria-label={label}
      className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 bg-gold text-cream font-sans font-semibold text-sm px-5 py-3 rounded-full shadow-lg hover:opacity-90 hover:-translate-y-0.5 transition-all sm:bottom-8 sm:right-8"
    >
      {icon}
      <span>{label}</span>
    </Link>
  );
}
