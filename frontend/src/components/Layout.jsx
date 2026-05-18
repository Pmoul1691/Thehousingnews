import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
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

function ChevronLeft() {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
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
        <div className="container-wide flex items-center justify-between gap-3 py-4">
          <div className="flex items-center gap-3 min-w-0">
            {authed && !isFeed && (
              <Link
                to="/feed"
                data-testid="header-back-to-feed"
                aria-label="Back to feed"
                title="Back to feed"
                className="hidden sm:inline-flex items-center justify-center w-9 h-9 rounded-sm border hairline text-muted-ink hover:text-gold hover:border-gold transition-colors shrink-0"
              >
                <ChevronLeft />
              </Link>
            )}
            <Link to="/" data-testid="nav-home" className="flex items-center gap-2.5 min-w-0">
              <img
                src="/brand/logo-full.png"
                alt="The Housing News"
                className="h-7 sm:h-9 w-auto select-none max-w-[55vw] sm:max-w-none"
                draggable={false}
              />
            </Link>
          </div>

          {/* Primary nav — visible on desktop only. Keeps the burger menu as a
              full sitemap, but exposes the four most-trafficked surfaces inline. */}
          <nav className="hidden md:flex items-center gap-6 mx-auto" aria-label="Primary">
            {authed ? (
              <>
                <Link to="/feed" data-testid="primary-nav-feed" className={`font-sans text-sm font-medium transition-colors ${loc.pathname === "/feed" ? "text-gold" : "ink hover:text-gold"}`}>Feed</Link>
                <Link to="/essays" data-testid="primary-nav-essays" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/essays") ? "text-gold" : "ink hover:text-gold"}`}>Essays</Link>
                <Link to="/members" data-testid="primary-nav-members" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/members") ? "text-gold" : "ink hover:text-gold"}`}>Members</Link>
                <Link to="/news" data-testid="primary-nav-news" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/news") ? "text-gold" : "ink hover:text-gold"}`}>News</Link>
              </>
            ) : (
              <>
                <Link to="/news" data-testid="primary-nav-news" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/news") ? "text-gold" : "ink hover:text-gold"}`}>News</Link>
                <Link to="/essays" data-testid="primary-nav-essays" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/essays") ? "text-gold" : "ink hover:text-gold"}`}>Essays</Link>
                <Link to="/subscribe" data-testid="primary-nav-subscribe" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/subscribe") ? "text-gold" : "ink hover:text-gold"}`}>Subscribe</Link>
                <Link to="/about" data-testid="primary-nav-about" className={`font-sans text-sm font-medium transition-colors ${loc.pathname.startsWith("/about") ? "text-gold" : "ink hover:text-gold"}`}>About</Link>
              </>
            )}
          </nav>

          <div className="flex items-center gap-3 sm:gap-5 shrink-0">
            {!hideHeaderTimer && <div className="hidden lg:block"><NextReleaseTimer /></div>}
            {authed && (
              <Link
                to="/write"
                data-testid="nav-write"
                className="inline-flex items-center gap-1.5 bg-gold text-cream font-sans font-semibold text-sm px-4 py-1.5 rounded-full hover:opacity-90 transition-opacity"
              >
                <WriteIcon />
                Write
              </Link>
            )}
            {!authed && !user && (
              <>
                <Link
                  to="/join"
                  data-testid="nav-apply"
                  className="inline-flex items-center bg-gold text-cream font-sans font-semibold text-sm px-4 py-1.5 rounded-full hover:opacity-90 transition-opacity"
                >
                  Join
                </Link>
                <Link
                  to="/signin"
                  data-testid="nav-signin"
                  className="hidden sm:inline font-sans text-sm font-medium ink hover:text-gold transition-colors"
                >
                  Sign in
                </Link>
              </>
            )}
            {user && !authed && (
              <button onClick={logout} data-testid="nav-logout" className="font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors">
                Sign out
              </button>
            )}
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
                  {authed && (
                    <>
                      <Link to="/essays" onClick={closeMenu} data-testid="menu-essays" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Essays</Link>
                      <Link to="/search" onClick={closeMenu} data-testid="menu-search" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Search</Link>
                      <Link to="/prompts" onClick={closeMenu} data-testid="menu-prompts" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Subjects</Link>
                      <Link to="/library" onClick={closeMenu} data-testid="menu-library" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Library</Link>
                      <Link to="/members" onClick={closeMenu} data-testid="menu-members" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Members</Link>
                      <Link to="/referrals" onClick={closeMenu} data-testid="menu-referrals" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Referrals</Link>
                      <Link to="/profile" onClick={closeMenu} data-testid="menu-profile" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Profile</Link>
                      <Link to="/settings" onClick={closeMenu} data-testid="menu-settings" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Settings</Link>
                      {user.is_admin && (
                        <Link to="/admin" onClick={closeMenu} data-testid="menu-admin" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Admin</Link>
                      )}
                    </>
                  )}
                  {!authed && !user && (
                    <>
                      <Link to="/join" onClick={closeMenu} data-testid="menu-apply" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Join</Link>
                      <Link
                        to="/signin"
                        onClick={closeMenu}
                        data-testid="menu-signin"
                        className="text-left font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors"
                      >
                        Sign in
                      </Link>
                    </>
                  )}
                  <Link to="/about" onClick={closeMenu} data-testid="menu-about" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">About</Link>
                  <Link to="/pricing" onClick={closeMenu} data-testid="menu-pricing" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">Pricing</Link>
                  <Link to="/news" onClick={closeMenu} data-testid="menu-news" className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors">News aggregator</Link>
                  <a
                    href="/legal/terms-of-service.pdf"
                    target="_blank"
                    rel="noreferrer"
                    onClick={closeMenu}
                    data-testid="menu-terms"
                    className="font-display text-xl ink px-4 py-3 rounded-sm hover:bg-[#F5EDD6]/60 hover:text-gold transition-colors"
                  >
                    Terms
                  </a>
                  {authed && (
                    <div className="border-t hairline mt-3 pt-3">
                      <button
                        onClick={() => { closeMenu(); logout(); }}
                        data-testid="menu-logout"
                        className="w-full text-left font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors px-4 py-2"
                      >
                        Sign out
                      </button>
                    </div>
                  )}
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main className="flex-1 pb-24 sm:pb-0">{children}</main>

      <footer className="border-t hairline mt-24">
        <div className="container-wide py-12 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <img
              src="/brand/logo-full.png"
              alt="The Housing News"
              className="h-10 w-auto select-none"
              draggable={false}
            />
            <div className="font-serif text-xs text-muted-ink">A daily magazine for the real estate industry.</div>
          </div>
          <div className="font-sans text-xs text-muted-ink max-w-md">
            Published by the editors. Read the <Link to="/about" className="hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">masthead</Link> or our <a href="/legal/terms-of-service.pdf" target="_blank" rel="noreferrer" data-testid="footer-terms-link" className="hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">Terms of Service</a>.
          </div>
        </div>
      </footer>
    </div>
  );
}
