import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";

/**
 * Aggregator layout — Techmeme-inspired chrome.
 * Deep navy header + single warm-orange accent. No hero images, no gradients.
 *
 * Used by aggregator pages only (/, /source/:slug, /category/:category,
 * /about, /newsletter, /admin/aggregator). Members product uses Layout.jsx
 * with its cream/gold theme.
 */

const CATEGORIES = [
  { key: null, label: "All" },
  { key: "national_trade", label: "National" },
  { key: "regional", label: "Regional" },
  { key: "industry_blog", label: "Blogs" },
  { key: "data_research", label: "Data" },
  { key: "mortgage", label: "Mortgage" },
  { key: "newsletter", label: "Newsletters" },
];

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="17" x2="20" y2="17" />
    </svg>
  );
}

export default function AggLayout({ children }) {
  const loc = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const close = () => setMenuOpen(false);
  const activeCategory = loc.pathname.startsWith("/news/category/") ? loc.pathname.split("/")[3] : null;
  const isHome = loc.pathname === "/news" || loc.pathname === "/news/";

  return (
    <div className="min-h-screen flex flex-col agg-bg">
      <header className="bg-agg-navy text-agg-cream border-b border-agg-navy-deep">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between py-3">
            <Link to="/news" data-testid="agg-nav-home" className="flex items-center gap-3 group">
              <img
                src="/brand/favicon-gold.svg"
                alt=""
                aria-hidden="true"
                className="h-7 sm:h-8 w-auto select-none"
                draggable={false}
              />
              <img
                src="/brand/logo-full-light.png"
                alt="The Housing News"
                className="h-7 sm:h-8 w-auto select-none"
                draggable={false}
              />
              <span className="hidden sm:inline font-sans text-[10px] uppercase tracking-[0.22em] text-agg-orange/90 mt-0.5">
                Daily aggregator
              </span>
            </Link>
            <div className="flex items-center gap-5">
              <Link to="/news/latest" data-testid="agg-nav-latest" className="hidden sm:inline font-sans text-sm font-medium text-agg-cream hover:text-agg-orange transition-colors">
                Latest
              </Link>
              <Link to="/news/podcasts" data-testid="agg-nav-podcasts" className="hidden sm:inline font-sans text-sm font-medium text-agg-cream hover:text-agg-orange transition-colors">
                Podcasts
              </Link>
              <Link to="/news/newsletter" data-testid="agg-nav-newsletter" className="hidden sm:inline font-sans text-sm font-medium text-agg-cream hover:text-agg-orange transition-colors">
                Newsletter
              </Link>
              <Link to="/news/about" data-testid="agg-nav-about" className="hidden sm:inline font-sans text-sm font-medium text-agg-cream hover:text-agg-orange transition-colors">
                About
              </Link>
              <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
                <SheetTrigger asChild>
                  <button
                    type="button"
                    data-testid="agg-nav-menu-trigger"
                    aria-label="Open menu"
                    className="inline-flex items-center justify-center w-9 h-9 rounded-sm border border-agg-navy-deep text-agg-cream hover:text-agg-orange hover:border-agg-orange transition-colors"
                  >
                    <MenuIcon />
                  </button>
                </SheetTrigger>
                <SheetContent
                  side="right"
                  className="bg-agg-navy border-l border-agg-navy-deep text-agg-cream w-[280px] sm:max-w-[300px] p-0"
                  data-testid="agg-nav-menu-sheet"
                >
                  <SheetTitle className="sr-only">Menu</SheetTitle>
                  <div className="px-6 pt-6 pb-3">
                    <p className="font-sans text-[10px] uppercase tracking-[0.22em] text-agg-orange/90 font-semibold">Menu</p>
                  </div>
                  <nav className="flex flex-col px-2 pb-6">
                    <Link to="/news" onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">Home</Link>
                    <Link to="/news/latest" onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">Latest</Link>
                    {CATEGORIES.filter(c => c.key).map(c => (
                      <Link key={c.key} to={`/news/category/${c.key}`} onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">
                        {c.label}
                      </Link>
                    ))}
                    <Link to="/news/podcasts" onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">Podcasts</Link>
                    <Link to="/news/newsletter" onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">Newsletter</Link>
                    <Link to="/news/about" onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">About</Link>
                    <a href="/legal/terms-of-service.pdf" target="_blank" rel="noreferrer" onClick={close} className="font-display text-lg px-4 py-3 rounded-sm hover:bg-agg-navy-deep hover:text-agg-orange transition-colors">Terms</a>
                    <div className="border-t border-agg-navy-deep mt-3 pt-3">
                      <Link to="/" onClick={close} className="block font-sans text-sm px-4 py-2 text-agg-cream/70 hover:text-agg-orange transition-colors">
                        Members club →
                      </Link>
                    </div>
                  </nav>
                </SheetContent>
              </Sheet>
            </div>
          </div>
          {/* Category filter bar */}
          <nav className="flex items-center gap-1 sm:gap-2 overflow-x-auto -mx-1 pb-2 sm:pb-3 text-sm" data-testid="agg-category-filter">
            {CATEGORIES.map(c => {
              const to = c.key === null ? "/news" : `/news/category/${c.key}`;
              const active = c.key === null ? isHome : activeCategory === c.key;
              return (
                <Link
                  key={c.label}
                  to={to}
                  data-testid={`agg-cat-${c.key || "all"}`}
                  className={`shrink-0 px-3 py-1 rounded-full font-sans text-[12px] uppercase tracking-[0.12em] font-semibold transition-colors ${
                    active ? "bg-agg-orange text-agg-navy" : "text-agg-cream/85 hover:text-agg-orange"
                  }`}
                >
                  {c.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8">{children}</main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-sm text-slate-600">
          <div>
            © {new Date().getFullYear()} The Housing News · A public RSS aggregator for the residential real estate industry.
          </div>
          <div className="flex items-center gap-5">
            <Link to="/news/about" className="hover:text-agg-orange transition-colors">About</Link>
            <Link to="/news/podcasts" className="hover:text-agg-orange transition-colors">Podcasts</Link>
            <Link to="/news/newsletter" className="hover:text-agg-orange transition-colors">Newsletter</Link>
            <a href="/legal/terms-of-service.pdf" target="_blank" rel="noreferrer" className="hover:text-agg-orange transition-colors">Terms</a>
            <Link to="/" className="hover:text-agg-orange transition-colors">Members</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
