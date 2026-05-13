import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import BloomMark from "@/components/BloomMark";
import NextReleaseTimer from "@/components/NextReleaseTimer";
import { useAuth } from "@/context/AuthContext";

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const navigate = useNavigate();
  const isLanding = loc.pathname === "/";
  const isFeed = loc.pathname === "/feed";
  const hideHeaderTimer = isLanding || isFeed;

  return (
    <div className="min-h-screen flex flex-col bg-cream ink">
      <header className="sticky top-0 z-30 backdrop-blur-md bg-cream/85 border-b hairline">
        <div className="container-wide flex items-center justify-between py-4">
          <Link to="/" data-testid="nav-home" className="flex items-center gap-3">
            <BloomMark size={28} />
            <span className="font-display font-semibold tracking-tight text-[15px] ink">The Ultradian Network</span>
          </Link>
          <div className="flex items-center gap-5">
            {!hideHeaderTimer && <div className="hidden sm:block"><NextReleaseTimer /></div>}
            {user && user.status === "approved" && (
              <>
                <Link to="/feed" data-testid="nav-feed" className="font-sans text-sm font-medium hover:text-gold transition-colors">Feed</Link>
                <Link to="/essays" data-testid="nav-essays" className="font-sans text-sm font-medium hover:text-gold transition-colors">Essays</Link>
                <Link to="/prompts" data-testid="nav-prompts" className="font-sans text-sm font-medium hover:text-gold transition-colors">Subjects</Link>
                <Link to="/library" data-testid="nav-library" className="font-sans text-sm font-medium hover:text-gold transition-colors">Library</Link>
                <Link to="/members" data-testid="nav-members" className="font-sans text-sm font-medium hover:text-gold transition-colors">Members</Link>
                <Link to="/profile" data-testid="nav-profile" className="font-sans text-sm font-medium hover:text-gold transition-colors">Profile</Link>
                {user.is_admin && (
                  <Link to="/admin" data-testid="nav-admin" className="font-sans text-sm font-medium hover:text-gold transition-colors">Admin</Link>
                )}
                <Link
                  to="/write"
                  data-testid="nav-write"
                  className="inline-flex items-center gap-1.5 bg-gold text-cream font-sans font-semibold text-sm px-4 py-1.5 rounded-full hover:opacity-90 transition-opacity"
                >
                  <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                  Write
                </Link>
              </>
            )}
            {user ? (
              <button onClick={logout} data-testid="nav-logout" className="font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors">
                Sign out
              </button>
            ) : (
              !isLanding && (
                <button
                  data-testid="nav-signin"
                  onClick={() => {
                    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
                    const redirectUrl = window.location.origin + "/auth/callback";
                    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
                  }}
                  className="font-sans text-sm font-medium ink hover:text-gold transition-colors"
                >
                  Sign in
                </button>
              )
            )}
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t hairline mt-24">
        <div className="container-wide py-12 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <BloomMark size={32} />
            <div>
              <div className="font-display font-semibold text-sm ink">The Ultradian Network</div>
              <div className="font-serif text-xs text-muted-ink">A calm place for real estate operators.</div>
            </div>
          </div>
          <div className="font-sans text-xs text-muted-ink max-w-md">
            Built by Pete Moulton. Sister properties: ultradianpartners.com and ultradia.io.
          </div>
        </div>
      </footer>
    </div>
  );
}
