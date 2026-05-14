import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import BloomMark from "@/components/BloomMark";

function fmt(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(iso));
  } catch { return ""; }
}

export default function Upgrade() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [sub, setSub] = useState(null);
  const [starting, setStarting] = useState(null);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    api.get("/me/subscription").then((r) => setSub(r.data));
  }, [user, loading, navigate]);

  const checkout = async (tier) => {
    setStarting(tier);
    try {
      const r = await api.post("/payments/checkout", { origin_url: window.location.origin, tier });
      window.location.href = r.data.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start checkout");
      setStarting(null);
    }
  };

  const isActive = sub?.is_supporter;
  const monthly = sub?.tiers?.find((t) => t.id === "monthly");
  const yearly = sub?.tiers?.find((t) => t.id === "yearly");
  const yearlyMonthly = yearly ? (yearly.amount / 12).toFixed(2) : null;
  const yearlySavings = (monthly && yearly) ? Math.round((1 - (yearly.amount / (monthly.amount * 12))) * 100) : 0;

  return (
    <div className="container-prose py-20 animate-fade-up">
      <div className="mb-10"><BloomMark size={64} /></div>
      <p className="uppercase-label mb-4">Support</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">
        Two ways to support the newsroom.
      </h1>
      <div className="prose-serif text-base sm:text-lg leading-relaxed ink/90 space-y-4 max-w-prose mb-12">
        <p>I run this myself. No ads. No data brokers. No engagement loops.</p>
        <p>Becoming a supporter pays for hosting and email, and lets us keep the membership free for new agents and producers who are starting out.</p>
        <p>Your name shows a small Bloom mark next to it on the feed. That is it. No tiers, no perks, no leaderboards.</p>
      </div>

      {isActive ? (
        <div className="border hairline rounded-sm p-6 bg-cream mb-10" data-testid="supporter-active">
          <p className="uppercase-label mb-2">You are a supporter</p>
          <p className="font-display font-semibold text-xl ink mb-2">Thank you.</p>
          <p className="font-serif text-base ink/80">Active through {fmt(sub.supporter_until)}.</p>
        </div>
      ) : null}

      {sub && (
        <div className="grid sm:grid-cols-2 gap-5" data-testid="tier-cards">
          {/* Monthly */}
          <div className="border hairline rounded-sm p-7 bg-cream flex flex-col" data-testid="tier-monthly">
            <p className="uppercase-label mb-3">{monthly?.label}</p>
            <div className="flex items-baseline gap-1 mb-2">
              <span className="font-display font-semibold text-4xl ink">${monthly?.amount?.toFixed(0)}</span>
              <span className="font-sans text-sm text-muted-ink">/month</span>
            </div>
            <p className="font-serif text-sm text-muted-ink mb-6">30 days each time. Renews when you say so.</p>
            <button
              data-testid="checkout-monthly"
              onClick={() => checkout("monthly")}
              disabled={starting === "monthly"}
              className="mt-auto inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {starting === "monthly" ? "Starting..." : isActive ? "Extend by 30 days" : "Pay monthly"}
            </button>
          </div>

          {/* Yearly */}
          <div className="border-2 border-gold rounded-sm p-7 bg-cream relative flex flex-col" data-testid="tier-yearly">
            {yearlySavings > 0 && (
              <span className="absolute -top-2.5 right-5 bg-gold text-cream font-sans text-[10px] uppercase tracking-wider font-semibold px-2 py-1 rounded-sm">Save {yearlySavings}%</span>
            )}
            <p className="uppercase-label mb-3">{yearly?.label}</p>
            <div className="flex items-baseline gap-1 mb-2">
              <span className="font-display font-semibold text-4xl ink">${yearly?.amount?.toFixed(0)}</span>
              <span className="font-sans text-sm text-muted-ink">/year</span>
            </div>
            <p className="font-serif text-sm text-muted-ink mb-6">
              {yearlyMonthly ? `Works out to $${yearlyMonthly} a month.` : ""} 365 days each time.
            </p>
            <button
              data-testid="checkout-yearly"
              onClick={() => checkout("yearly")}
              disabled={starting === "yearly"}
              className="mt-auto inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {starting === "yearly" ? "Starting..." : isActive ? "Extend by a year" : "Pay yearly"}
            </button>
          </div>
        </div>
      )}
      <p className="font-sans text-xs text-muted-ink mt-6">Pay once. Renews manually whenever you want.</p>
    </div>
  );
}
