import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const MODES = [
  { k: "magic", l: "Magic link" },
  { k: "password", l: "Email + password" },
];

function googleSignIn() {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS — this breaks the auth.
  const redirectUrl = window.location.origin + "/auth/callback";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
}

function formatErr(detail) {
  if (!detail) return "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function SignIn() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const mode = params.get("mode") || "magic";
  const [tab, setTab] = useState(MODES.find((m) => m.k === mode) ? mode : "magic");
  const [pwMode, setPwMode] = useState("signin"); // signin | signup
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [magicSent, setMagicSent] = useState(false);

  const afterAuth = async () => {
    const r = await refresh();
    // /feed for approved, /join for needs_application, default landing for else.
    const data = r?.data || null;
    void data; // refresh() updates context — let the next route guard route.
    navigate("/feed", { replace: true });
  };

  const sendMagic = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      await api.post("/auth/magic-link/request", { email: email.trim().toLowerCase() });
      setMagicSent(true);
    } catch (err) {
      toast.error(formatErr(err?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const submitPassword = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const path = pwMode === "signup" ? "/auth/email/signup" : "/auth/email/signin";
      const payload = pwMode === "signup"
        ? { email: email.trim().toLowerCase(), password, name: name.trim() || undefined }
        : { email: email.trim().toLowerCase(), password };
      const r = await api.post(path, payload);
      if (pwMode === "signup" && r?.data?.verification_email_sent) {
        toast.success("Account created. Check your inbox to verify your email.");
      } else {
        toast.success("Signed in.");
      }
      await afterAuth();
    } catch (err) {
      toast.error(formatErr(err?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const requestReset = async () => {
    if (!email.trim()) {
      toast.error("Enter your email first.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/password/reset/request", { email: email.trim().toLowerCase() });
      toast.success("If an account exists, a reset link is on its way.");
    } catch (err) {
      toast.error(formatErr(err?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="container-prose py-16 sm:py-20 animate-fade-up">
      <p className="uppercase-label mb-3">Sign in</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-4">Welcome back.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed mb-10 max-w-prose">
        Three ways in. Pick whichever you like.
      </p>

      {/* Google */}
      <button
        type="button"
        onClick={googleSignIn}
        data-testid="signin-google-btn"
        className="w-full sm:w-auto inline-flex items-center justify-center gap-3 border hairline rounded-sm bg-white px-5 py-3 font-sans font-semibold text-sm ink hover:border-gold hover:text-gold transition-colors mb-3 sm:mr-3"
      >
        <svg viewBox="0 0 24 24" className="w-4 h-4" aria-hidden="true">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.07 5.07 0 0 1-2.2 3.32v2.77h3.56c2.08-1.92 3.28-4.74 3.28-8.1z" />
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.77c-.99.66-2.25 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
          <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.48 12c0-.73.13-1.44.36-2.1V7.07H2.18A11 11 0 0 0 1 12c0 1.78.43 3.46 1.18 4.93l3.66-2.83z" />
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.2 1.64l3.15-3.15C17.45 2.07 14.97 1 12 1A11 11 0 0 0 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
        </svg>
        Continue with Google
      </button>

      <div className="flex items-center gap-3 my-8" aria-hidden="true">
        <div className="h-px bg-gold/20 flex-1" />
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-ink">or with email</span>
        <div className="h-px bg-gold/20 flex-1" />
      </div>

      {/* Mode toggle */}
      <div className="flex items-center gap-2 mb-6">
        {MODES.map((m) => (
          <button
            key={m.k}
            type="button"
            data-testid={`signin-mode-${m.k}`}
            onClick={() => { setTab(m.k); setMagicSent(false); }}
            className={`font-sans text-xs uppercase tracking-[0.18em] font-semibold px-3 py-2 rounded-full transition-colors ${
              tab === m.k ? "bg-ink text-cream" : "border hairline text-muted-ink hover:text-ink"
            }`}
          >
            {m.l}
          </button>
        ))}
      </div>

      {tab === "magic" && (
        magicSent ? (
          <div data-testid="signin-magic-sent" className="border hairline rounded-sm p-6 bg-cream/60">
            <p className="uppercase-label mb-2">Check your inbox</p>
            <p className="font-serif text-base ink/85 leading-relaxed">
              We sent a sign-in link to <strong>{email}</strong>. It expires in 15 minutes.
            </p>
            <button
              type="button"
              onClick={() => setMagicSent(false)}
              className="mt-4 font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity"
            >
              Use a different email →
            </button>
          </div>
        ) : (
          <form onSubmit={sendMagic} className="space-y-4" data-testid="signin-magic-form">
            <div>
              <label className="block uppercase-label mb-2">Email</label>
              <input
                data-testid="signin-magic-email"
                type="email"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
              />
            </div>
            <button
              type="submit"
              disabled={busy || !email.trim()}
              data-testid="signin-magic-submit"
              className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busy ? "Sending…" : "Email me a sign-in link"}
            </button>
            <p className="font-sans text-xs text-muted-ink">
              No password. We email you a link, you click it, you're in.
            </p>
          </form>
        )
      )}

      {tab === "password" && (
        <form onSubmit={submitPassword} className="space-y-4" data-testid="signin-password-form">
          <div className="flex items-center gap-2 mb-2">
            {["signin", "signup"].map((m) => (
              <button
                key={m}
                type="button"
                data-testid={`signin-pwmode-${m}`}
                onClick={() => setPwMode(m)}
                className={`font-sans text-[11px] uppercase tracking-[0.18em] font-semibold px-3 py-1.5 rounded-full transition-colors ${
                  pwMode === m ? "bg-gold text-cream" : "border hairline text-muted-ink hover:text-ink"
                }`}
              >
                {m === "signin" ? "I have an account" : "Create account"}
              </button>
            ))}
          </div>
          {pwMode === "signup" && (
            <div>
              <label className="block uppercase-label mb-2">Name (optional)</label>
              <input
                data-testid="signin-pw-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Smith"
                className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
              />
            </div>
          )}
          <div>
            <label className="block uppercase-label mb-2">Email</label>
            <input
              data-testid="signin-pw-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
            />
          </div>
          <div>
            <label className="block uppercase-label mb-2">Password</label>
            <input
              data-testid="signin-pw-password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={pwMode === "signup" ? "At least 8 characters" : "Your password"}
              className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
            />
          </div>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <button
              type="submit"
              disabled={busy || !email.trim() || password.length < 8}
              data-testid="signin-pw-submit"
              className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busy ? "…" : pwMode === "signup" ? "Create account" : "Sign in"}
            </button>
            {pwMode === "signin" && (
              <button
                type="button"
                onClick={requestReset}
                data-testid="signin-forgot"
                className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-gold transition-colors"
              >
                Forgot password?
              </button>
            )}
          </div>
        </form>
      )}

      <p className="font-sans text-xs text-muted-ink mt-12">
        New here? <Link to="/join" className="text-gold hover:opacity-80 underline underline-offset-4 decoration-gold-mid">Tell us about you</Link> after you sign in.
      </p>
    </div>
  );
}
