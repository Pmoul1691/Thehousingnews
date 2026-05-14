import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";

const STATIC_TIERS = [
  { id: "monthly", label: "Monthly", amount: 12.5, period: "month", note: "30 days each time." },
  { id: "yearly", label: "Annual", amount: 100, period: "year", note: "365 days. Works out to $8.33 a month.", featured: true },
];

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
      // Not signed in — send to auth flow
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
          Just sign in with the same email — your membership is automatically granted.
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
          New to The Housing News? <Link to="/apply" className="text-gold hover:opacity-80 transition-opacity underline underline-offset-4 decoration-gold-mid">Apply for membership</Link>.
        </p>
      </div>
    </div>
  );
}
