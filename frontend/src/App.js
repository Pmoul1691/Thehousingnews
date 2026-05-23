import React, { Suspense, lazy } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";

// Members-product layout (cream + gold)
import Layout from "@/components/Layout";
// Aggregator layout (Techmeme navy + orange)
import AggLayout from "@/components/AggLayout";
// Global member-only profile-completion nudge
import ProfileNudgeBanner from "@/components/ProfileNudgeBanner";

// Eager pages: landing, sign-in, auth callback, and the two highest-traffic
// content surfaces (AggHome / Today). Everything below the fold of common
// flows is lazy-loaded so first-time visitors don't pay for 38 routes worth
// of JS just to see the home page.
import Landing from "@/pages/Landing";
import AuthCallback from "@/pages/AuthCallback";
import SignIn from "@/pages/SignIn";
import AggHome from "@/pages/AggHome";
import usePageviewTracker from "@/hooks/usePageviewTracker";
import FloatingWriteButton from "@/components/FloatingWriteButton";
import ReadWriteToggle from "@/components/ReadWriteToggle";
import FloatingSuggestButton from "@/components/FloatingSuggestButton";

// Lazy-loaded pages — each becomes its own webpack chunk that the browser
// only fetches when the user actually navigates to that route. The
// <Suspense> fallback at the route level keeps the page chrome up while the
// chunk loads, so the experience reads as "instant nav, brief skeleton" not
// "full-page replacement".
const About = lazy(() => import("@/pages/About"));
const Join = lazy(() => import("@/pages/Join"));
const PendingReview = lazy(() => import("@/pages/PendingReview"));
const Declined = lazy(() => import("@/pages/Declined"));
const Onboarding = lazy(() => import("@/pages/Onboarding"));
const Feed = lazy(() => import("@/pages/Feed"));
const PublicFeed = lazy(() => import("@/pages/PublicFeed"));
const Profile = lazy(() => import("@/pages/Profile"));
const Directory = lazy(() => import("@/pages/Directory"));
const Referrals = lazy(() => import("@/pages/Referrals"));
const Settings = lazy(() => import("@/pages/Settings"));
const EssayDetail = lazy(() => import("@/pages/EssayDetail"));
const Essays = lazy(() => import("@/pages/Essays"));
const Library = lazy(() => import("@/pages/Library"));
const Write = lazy(() => import("@/pages/Write"));
const Admin = lazy(() => import("@/pages/Admin"));
const EmailHealth = lazy(() => import("@/pages/EmailHealth"));
const AdminDrafts = lazy(() => import("@/pages/AdminDrafts"));
const Prompts = lazy(() => import("@/pages/Prompts"));
const PromptDetail = lazy(() => import("@/pages/PromptDetail"));
const Search = lazy(() => import("@/pages/Search"));
const Tag = lazy(() => import("@/pages/Tag"));
const Claim = lazy(() => import("@/pages/Claim"));
const Today = lazy(() => import("@/pages/Today"));
const Subscribe = lazy(() => import("@/pages/Subscribe"));
const VerifyEmail = lazy(() => import("@/pages/VerifyEmail"));
const MagicLinkConsume = lazy(() => import("@/pages/MagicLinkConsume"));
const ResetPassword = lazy(() => import("@/pages/ResetPassword"));

// Aggregator sub-pages (only AggHome stays eager; the rest split out).
const AggLatest = lazy(() => import("@/pages/AggLatest"));
const AggPublisher = lazy(() => import("@/pages/AggPublisher"));
const AggCategory = lazy(() => import("@/pages/AggCategory"));
const AggAbout = lazy(() => import("@/pages/AggAbout"));
const AggNewsletter = lazy(() => import("@/pages/AggNewsletter"));
const AggAdmin = lazy(() => import("@/pages/AggAdmin"));
const Podcasts = lazy(() => import("@/pages/Podcasts"));

// Paths owned by the aggregator. Everything else falls back to the members
// product layout. Keep this list in sync with the routes below.
const AGG_PATHS = [/^\/news(\/|$)/, /^\/admin\/aggregator$/];

function isAggregatorPath(pathname) {
  return AGG_PATHS.some((re) => re.test(pathname));
}

// Lightweight, layout-neutral fallback shown while a lazy chunk is fetching.
// Intentionally minimal so it never flashes obtrusively — most chunks land
// in <200 ms on a warm CDN.
function RouteFallback() {
  return (
    <div
      data-testid="route-fallback"
      className="min-h-[60vh] flex items-center justify-center"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="w-6 h-6 rounded-full border-2 border-slate-200 border-t-slate-500 animate-spin" />
    </div>
  );
}

function Router() {
  const location = useLocation();
  usePageviewTracker();
  // Handle session_id during render to avoid race with AuthProvider
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }

  const ChromeLayout = isAggregatorPath(location.pathname) ? AggLayout : Layout;

  return (
    <ChromeLayout>
      <ProfileNudgeBanner />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* === Members product (owns /) === */}
          <Route path="/" element={<Landing />} />
          <Route path="/today" element={<Today />} />
          <Route path="/members" element={<Directory />} />
          <Route path="/about" element={<About />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/auth/verify-email" element={<VerifyEmail />} />
          <Route path="/auth/magic" element={<MagicLinkConsume />} />
          <Route path="/auth/reset-password" element={<ResetPassword />} />
          <Route path="/join" element={<Join />} />
          <Route path="/subscribe" element={<Subscribe />} />
          <Route path="/pending" element={<PendingReview />} />
          <Route path="/declined" element={<Declined />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/feed" element={<Feed />} />
          <Route path="/public" element={<PublicFeed />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/profile/:id" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/referrals" element={<Referrals />} />
          <Route path="/essays" element={<Essays />} />
          <Route path="/essays/:id" element={<EssayDetail />} />
          <Route path="/library" element={<Library />} />
          <Route path="/write" element={<Write />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/admin/email-health" element={<EmailHealth />} />
          <Route path="/admin/drafts" element={<AdminDrafts />} />
          <Route path="/prompts" element={<Prompts />} />
          <Route path="/prompts/:id" element={<PromptDetail />} />
          <Route path="/search" element={<Search />} />
          <Route path="/tag/:tag" element={<Tag />} />
          <Route path="/claim" element={<Claim />} />

          {/* === Aggregator (lives under /news) === */}
          <Route path="/news" element={<AggHome />} />
          <Route path="/news/latest" element={<AggLatest />} />
          <Route path="/news/source/:slug" element={<AggPublisher />} />
          <Route path="/news/category/:category" element={<AggCategory />} />
          <Route path="/news/about" element={<AggAbout />} />
          <Route path="/news/newsletter" element={<AggNewsletter />} />
          <Route path="/news/podcasts" element={<Podcasts />} />
          <Route path="/admin/aggregator" element={<AggAdmin />} />

          {/* === Back-compat redirects from the previous routing === */}
          <Route path="/welcome" element={<Navigate to="/" replace />} />
          <Route path="/welcome/about" element={<Navigate to="/about" replace />} />
          <Route path="/source/:slug" element={<LegacyAggRedirect to="/news/source" />} />
          <Route path="/category/:category" element={<LegacyAggRedirect to="/news/category" />} />
          <Route path="/newsletter" element={<Navigate to="/news/newsletter" replace />} />
        </Routes>
      </Suspense>
      <FloatingWriteButton />
      <ReadWriteToggle />
      <FloatingSuggestButton />
    </ChromeLayout>
  );
}

// Preserves the slug/category param across the redirect.
function LegacyAggRedirect({ to }) {
  const { pathname, search } = useLocation();
  const tail = pathname.split("/").slice(2).join("/");
  return <Navigate to={`${to}/${tail}${search}`} replace />;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Router />
          <Toaster
            position="bottom-center"
            duration={2200}
            toastOptions={{
              style: {
                background: "#FDFAF4",
                color: "#2C2410",
                border: "1px solid #E8D4A0",
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontSize: "12px",
                boxShadow: "none",
              },
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
