import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";

// Members-product layout (cream + gold)
import Layout from "@/components/Layout";
// Aggregator layout (Techmeme navy + orange)
import AggLayout from "@/components/AggLayout";

// Members product pages
import Landing from "@/pages/Landing";
import About from "@/pages/About";
import AuthCallback from "@/pages/AuthCallback";
import Apply from "@/pages/Apply";
import PendingReview from "@/pages/PendingReview";
import Declined from "@/pages/Declined";
import Onboarding from "@/pages/Onboarding";
import Feed from "@/pages/Feed";
import PublicFeed from "@/pages/PublicFeed";
import Profile from "@/pages/Profile";
import Members from "@/pages/Members";
import Settings from "@/pages/Settings";
import Upgrade from "@/pages/Upgrade";
import UpgradeSuccess from "@/pages/UpgradeSuccess";
import EssayDetail from "@/pages/EssayDetail";
import Essays from "@/pages/Essays";
import Library from "@/pages/Library";
import Write from "@/pages/Write";
import Admin from "@/pages/Admin";
import EmailHealth from "@/pages/EmailHealth";
import Prompts from "@/pages/Prompts";
import PromptDetail from "@/pages/PromptDetail";
import Search from "@/pages/Search";
import Pricing from "@/pages/Pricing";

// Aggregator pages
import AggHome from "@/pages/AggHome";
import AggPublisher from "@/pages/AggPublisher";
import AggCategory from "@/pages/AggCategory";
import AggAbout from "@/pages/AggAbout";
import AggNewsletter from "@/pages/AggNewsletter";
import AggAdmin from "@/pages/AggAdmin";

// Paths owned by the aggregator. Everything else falls back to the members
// product layout. Keep this list in sync with the routes below.
const AGG_PATHS = [/^\/$/, /^\/source\//, /^\/category\//, /^\/about$/, /^\/newsletter$/, /^\/admin\/aggregator$/];

function isAggregatorPath(pathname) {
  return AGG_PATHS.some((re) => re.test(pathname));
}

function Router() {
  const location = useLocation();
  // Handle session_id during render to avoid race with AuthProvider
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }

  const ChromeLayout = isAggregatorPath(location.pathname) ? AggLayout : Layout;

  return (
    <ChromeLayout>
      <Routes>
        {/* === Aggregator routes (public, no auth) === */}
        <Route path="/" element={<AggHome />} />
        <Route path="/source/:slug" element={<AggPublisher />} />
        <Route path="/category/:category" element={<AggCategory />} />
        <Route path="/about" element={<AggAbout />} />
        <Route path="/newsletter" element={<AggNewsletter />} />
        <Route path="/admin/aggregator" element={<AggAdmin />} />

        {/* === Members product routes (existing) === */}
        <Route path="/welcome" element={<Landing />} />
        <Route path="/welcome/about" element={<About />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/apply" element={<Apply />} />
        <Route path="/pending" element={<PendingReview />} />
        <Route path="/declined" element={<Declined />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/feed" element={<Feed />} />
        <Route path="/public" element={<PublicFeed />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/profile/:id" element={<Profile />} />
        <Route path="/members" element={<Members />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/upgrade" element={<Upgrade />} />
        <Route path="/upgrade/success" element={<UpgradeSuccess />} />
        <Route path="/essays" element={<Essays />} />
        <Route path="/essays/:id" element={<EssayDetail />} />
        <Route path="/library" element={<Library />} />
        <Route path="/write" element={<Write />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/admin/email-health" element={<EmailHealth />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/prompts/:id" element={<PromptDetail />} />
        <Route path="/search" element={<Search />} />
        <Route path="/pricing" element={<Pricing />} />
      </Routes>
    </ChromeLayout>
  );
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
