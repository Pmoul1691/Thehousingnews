import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import BloomMark from "@/components/BloomMark";
import NextReleaseTimer from "@/components/NextReleaseTimer";
import { useAuth } from "@/context/AuthContext";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="17" x2="20" y2="17" />
    </svg>
  );
}

function WriteIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const isLanding = loc.pathname === "/";
  const isFeed = loc.pathname === "/feed";
  const hideHeaderTimer = isLanding || isFeed;
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);
  const authed = user && user.status === "approved";

  return (
    <div className="min-h-screen flex flex-col bg-cream ink">
      <header className="sticky top-0 z-30 backdrop-blur-md bg-cream/85 border-b hairline">
        <div className="container-wide flex items-center justify-between py-4">
          <Link to="/" data-testid="nav-home" className="flex items-center gap-3">
            <BloomMark size={28} />
            <span className="font-display font-semibold tracking-tight text-[15px] ink">The Housing News</span>
          </Link>
          <div className="flex items-center gap-5">
            {!hideHeaderTimer && <div className="hidden sm:block"><NextReleaseTimer /></div>}
            {authed && (
              <>
                <Link to="/feed" data-testid="nav-feed" className="font-sans text-sm font-medium hover:text-gold transition-colors">Feed</Link>
                <Link
                  to="/write"
                  data-testid="nav-write"
                  className="inline-flex items-center gap-1.5 bg-gold text-cream font-sans font-semibold text-sm px-4 py-1.5 rounded-full hover:opacity-90 transition-opacity"
                >
                  <WriteIcon />
                  Write
                </Link>
                <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
                  <SheetTrigger asChild>
                    <button
                      type="button"
                      data-testid="nav-menu-trigger"
                      aria-label="Open menu"
                      className="inline-flex items-center justify-center w-9 h-9 rounded-sm border hairline text-ink hover:text-gold hover:border-gold transition-colors"
                    >
                      <MenuIcon />
                    </button>
                  </SheetTrigger>
                  <SheetContent
                    side="right"
                    className="bg-cream border-l hairline w-[300px] sm:max-w-[320px] p-0"
                    data-testid="nav-menu-sheet"
                  >
                    <SheetTitle className="sr-only">Menu</SheetTitle>
                    <div className="px-6 pt-6 pb-3">
                      <p className="uppercase-label">Menu</p>
                    </div>
                    <nav className="flex flex-col px-2 pb-6">
                      <Link to="/essays" onClick={closeMenu} data-testid="menu-essays" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        Essays
                      </Link>
                      <Link to="/prompts" onClick={closeMenu} data-testid="menu-prompts" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        Subjects
                      </Link>
                      <Link to="/library" onClick={closeMenu} data-testid="menu-library" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        Library
                      </Link>
                      <Link to="/members" onClick={closeMenu} data-testid="menu-members" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        Members
                      </Link>
                      <Link to="/profile" onClick={closeMenu} data-testid="menu-profile" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        Profile
                      </Link>
                      <Link to="/settings" onClick={closeMenu} data-testid="menu-settings" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        Settings
                      </Link>
                      {user.is_admin && (
                        <Link to="/admin" onClick={closeMenu} data-testid="menu-admin" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                          Admin
                        </Link>
                      )}
                      <Link to="/about" onClick={closeMenu} data-testid="menu-about" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">
                        About
                      </Link>
                      <div className="border-t hairline mt-3 pt-3">
                        <button
                          onClick={() => { closeMenu(); logout(); }}
                          data-testid="menu-logout"
                          className="w-full text-left font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors px-4 py-2"
                        >
                          Sign out
                        </button>
                      </div>
                    </nav>
                  </SheetContent>
                </Sheet>
              </>
            )}
            {!user && !isLanding && (
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
            )}
            {user && !authed && (
              <button onClick={logout} data-testid="nav-logout" className="font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors">
                Sign out
              </button>
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
              <div className="font-display font-semibold text-sm ink">The Housing News</div>
              <div className="font-serif text-xs text-muted-ink">A daily magazine for the real estate industry.</div>
            </div>
          </div>
          <div className="font-sans text-xs text-muted-ink max-w-md">
            Published by the editors. Read the <Link to="/about" className="hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">masthead</Link>.
          </div>
        </div>
      </footer>
    </div>
  );
}
