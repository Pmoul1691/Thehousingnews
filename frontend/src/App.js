import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import Layout from "@/components/Layout";
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

function Router() {
  const location = useLocation();
  // Handle session_id during render to avoid race with AuthProvider
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
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
      </Routes>
    </Layout>
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
