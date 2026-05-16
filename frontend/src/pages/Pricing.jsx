import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";

const STATIC_TIERS = [
  { id: "monthly", label: "Monthly", amount: 12.5, period: "month", note: "30 days each time." },
  { id: "yearly", label: "Annual", amount: 100, period: "year", note: "365 days. Works out to $8.33 a month.", featured: true },
];

const PROPERTY_LABELS = {
  ultradianpartners: "Ultradian Partners",
  "ultradia.io": "Ultradia.io",
  ultradia: "Ultradia.io",
};

function formatProperty(p) {
  if (!p) return "subscriber";
  const key = String(p).toLowerCase();
  return PROPERTY_LABELS[key] || p;
}

function prettyTier(tier) {
  if (!tier) return "";
  const t = String(tier).trim();
  // Capitalise first letter of each word
  return t.replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatRenewal(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric" }).format(d);
  } catch {
    return iso;
  }
}

function PartnerStatusCheck() {
  const [email, setEmail] = useState("");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const signIn = () => {
    const redirectUrl = window.location.origin + "/auth/callback";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setChecking(true);
    try {
      const r = await api.get("/partners/check", { params: { email: email.trim() } });
      setResult(r.data);
    } catch (e2) {
      setError(e2?.response?.data?.detail || "Could not check status. Try again in a minute.");
    } finally {
      setChecking(false);
    }
  };

  return (
    <section
      className="border hairline rounded-sm p-6 sm:p-7 bg-cream mb-10"
      data-testid="partner-status-check"
    >
      <p className="uppercase-label mb-2">Already a subscriber?</p>
      <h2 className="font-display font-semibold text-xl ink mb-2">Check your status.</h2>
      <p className="font-serif text-sm text-muted-ink mb-4 max-w-prose">
        Drop your Ultradian Partners or Ultradia.io email and we&apos;ll tell you if your membership here is already comped.
      </p>
      <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-3">
        <input
          type="email"
          required
          autoComplete="email"
          data-testid="partner-check-email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourdomain.com"
          className="flex-1 bg-cream border hairline rounded-sm px-4 py-3 font-serif text-base ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <button
          type="submit"
          disabled={checking || !email.trim()}
          data-testid="partner-check-submit"
          className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {checking ? "Checking." : "Check status"}
        </button>
      </form>

      {error && (
        <div data-testid="partner-check-error" className="mt-4 font-serif text-sm text-deepred">
          {error}
        </div>
      )}

      {result && result.comped && (
        <div
          data-testid="partner-check-result-comped"
          className="mt-5 border-l-2 border-gold pl-5 py-3 bg-[#FBF6E8]/50"
        >
          <p className="font-display font-semibold text-base ink mb-2">
            Good news{result.name ? `, ${result.name}` : ""}. You are already in.
          </p>
          <div className="flex flex-wrap items-center gap-2 mb-3" data-testid="partner-check-badge">
            <span className="inline-flex items-center gap-1.5 bg-gold/15 border border-gold/40 text-ink font-sans text-[11px] uppercase tracking-[0.14em] font-semibold px-2.5 py-1 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-gold" aria-hidden />
              Verified {formatProperty(result.property)}
              {result.tier ? ` · ${prettyTier(result.tier)}` : ""}
            </span>
            {result.renews_at && (
              <span className="font-sans text-xs text-muted-ink" data-testid="partner-check-renews">
                Auto-renews {formatRenewal(result.renews_at)}
              </span>
            )}
          </div>
          <p className="font-serif text-sm ink/80">
            Your subscription comps your membership at The Housing News.
          </p>
          <button
            onClick={signIn}
            data-testid="partner-check-signin"
            className="mt-3 inline-flex items-center gap-1.5 font-sans text-sm font-semibold text-gold hover:opacity-80 transition-opacity"
          >
            Sign in to read <span aria-hidden>→</span>
          </button>
        </div>
      )}

      {result && !result.comped && (
        <div
          data-testid="partner-check-result-none"
          className="mt-5 border-l-2 border-muted-ink/40 pl-4 py-2"
        >
          <p className="font-serif text-sm ink/80 mb-2">
            We do not see a current Ultradian Partners or Ultradia.io subscription for{" "}
            <span className="font-mono text-xs ink">{result.email}</span>.
          </p>
          <p className="font-serif text-sm text-muted-ink">
            You can still <Link to="/apply" className="text-gold underline underline-offset-4 decoration-gold-mid hover:opacity-80 transition-opacity">join now</Link>{" "}
            or pick a tier below.
          </p>
        </div>
      )}
    </section>
  );
}

export default function Pricing() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [tiers, setTiers] = useState(STATIC_TIERS);
  const [isSupporter, setIsSupporter] = useState(false);
  const [starting, setStarting] = useState(null);

  useEffect(() => {
    if (loading) return;
    if (user && user.status === "approved") {
      api.get("/me/subscription").then((r) => {
        const fromApi = r?.data?.tiers || [];
        if (fromApi.length) {
          setTiers(
            fromApi.map((t) => ({
              ...t,
              period: t.period_days === 365 ? "year" : "month",
              note: t.period_days === 365 ? "365 days. Works out to $8.33 a month." : "30 days each time.",
              featured: t.id === "yearly",
            }))
          );
        }
        setIsSupporter(!!r?.data?.is_supporter);
      }).catch(() => {});
    }
  }, [user, loading]);

  const checkout = async (tier) => {
    if (!user) {
      const redirectUrl = window.location.origin + "/auth/callback";
      window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
      return;
    }
    if (user.status !== "approved") {
      navigate("/apply");
      return;
    }
    setStarting(tier);
    try {
      const r = await api.post("/payments/checkout", { origin_url: window.location.origin, tier });
      window.location.href = r.data.url;
    } catch {
      setStarting(null);
    }
  };

  const partnerTier = user?.partner_tier;
  const partnerComped = !!partnerTier;

  return (
    <div className="container-prose py-20 animate-fade-up" data-testid="pricing-page">
      <p className="uppercase-label mb-4">Pricing</p>
      <h1 className="font-display font-semibold text-3xl sm:text-5xl ink mb-6 leading-tight">
        Calm reading. Honest pricing.
      </h1>
      <div className="prose-serif text-base sm:text-lg leading-relaxed ink/90 space-y-4 max-w-prose mb-12">
        <p>The Housing News is members-only. We keep it small, calm, and free of ads, trackers, and engagement loops.</p>
        <p>
          <strong className="font-display font-semibold">Free for existing Ultradian Partners clients and Ultradia.io subscribers.</strong>{" "}
          Just sign in with the same email &mdash; your membership is automatically granted.
        </p>
      </div>

      {partnerComped && (
        <div
          className="border-2 border-gold rounded-sm p-6 bg-[#FBF6E8] mb-10"
          data-testid="pricing-partner-banner"
        >
          <p className="uppercase-label mb-2">You are already in</p>
          <p className="font-display font-semibold text-lg ink mb-1">Welcome, partner.</p>
          <p className="font-serif text-base ink/80">
            Your membership is comped through your Ultradian Partners / Ultradia.io subscription. Nothing else to do.
          </p>
        </div>
      )}

      {!user && <PartnerStatusCheck />}

      {isSupporter && !partnerComped && (
        <div className="border hairline rounded-sm p-5 bg-cream mb-10" data-testid="pricing-supporter-banner">
          <p className="uppercase-label mb-2">You are a supporter</p>
          <p className="font-serif text-base ink/80">Thank you. Your support keeps the lights on.</p>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-5" data-testid="pricing-tiers">
        {tiers.map((t) => (
          <div
            key={t.id}
            data-testid={`pricing-tier-${t.id}`}
            className={
              t.featured
                ? "border-2 border-gold rounded-sm p-7 bg-cream relative flex flex-col"
                : "border hairline rounded-sm p-7 bg-cream flex flex-col"
            }
          >
            {t.featured && (
              <span className="absolute -top-2.5 right-5 bg-gold text-cream font-sans text-[10px] uppercase tracking-wider font-semibold px-2 py-1 rounded-sm">
                Best value
              </span>
            )}
            <p className="uppercase-label mb-3">{t.label}</p>
            <div className="flex items-baseline gap-1 mb-2">
              <span className="font-display font-semibold text-4xl ink">${Number(t.amount).toFixed(2)}</span>
              <span className="font-sans text-sm text-muted-ink">/ {t.period}</span>
            </div>
            <p className="font-serif text-sm text-muted-ink mb-6">{t.note}</p>
            <button
              data-testid={`pricing-checkout-${t.id}`}
              onClick={() => checkout(t.id)}
              disabled={starting === t.id || partnerComped}
              className="mt-auto inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {partnerComped
                ? "Included"
                : starting === t.id
                ? "Starting..."
                : !user
                ? "Sign in to subscribe"
                : user.status !== "approved"
                ? "Apply to subscribe"
                : isSupporter
                ? `Extend by a ${t.period}`
                : `Pay ${t.label.toLowerCase()}`}
            </button>
          </div>
        ))}
      </div>

      <div className="mt-12 border-t hairline pt-8 space-y-2">
        <p className="font-sans text-xs text-muted-ink">Pay once. Renews manually whenever you want.</p>
        <p className="font-sans text-xs text-muted-ink">
          New to The Housing News? <Link to="/apply" className="text-gold hover:opacity-80 transition-opacity underline underline-offset-4 decoration-gold-mid">Join now</Link>.
        </p>
      </div>
    </div>
  );
}
