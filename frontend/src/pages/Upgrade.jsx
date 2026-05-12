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
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    api.get("/me/subscription").then((r) => setSub(r.data));
  }, [user, loading, navigate]);

  const checkout = async () => {
    setStarting(true);
    try {
      const r = await api.post("/payments/checkout", { origin_url: window.location.origin });
      window.location.href = r.data.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start checkout");
      setStarting(false);
    }
  };

  const isActive = sub?.is_supporter;

  return (
    <div className="container-prose py-20 animate-fade-up">
      <div className="mb-10"><BloomMark size={64} /></div>
      <p className="uppercase-label mb-4">Support</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">
        ${sub?.price_usd?.toFixed(2) || "19.00"} a month. <br className="hidden sm:block" />Keeps the room small.
      </h1>
      <div className="prose-serif text-base sm:text-lg leading-relaxed ink/90 space-y-4 max-w-prose mb-10">
        <p>I run this myself. No ads. No data brokers. No engagement loops.</p>
        <p>Becoming a supporter pays for hosting and email, and lets me keep the membership free for new agents and operators who are starting out.</p>
        <p>Your name shows a small Bloom mark next to it on the feed. That is it. No tiers, no perks, no leaderboards.</p>
      </div>

      {isActive ? (
        <div className="border hairline rounded-sm p-6 bg-cream" data-testid="supporter-active">
          <p className="uppercase-label mb-2">You are a supporter</p>
          <p className="font-display font-semibold text-xl ink mb-2">Thank you.</p>
          <p className="font-serif text-base ink/80">Active through {fmt(sub.supporter_until)}.</p>
          <button
            data-testid="upgrade-extend-btn"
            onClick={checkout}
            disabled={starting}
            className="mt-6 inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {starting ? "Starting..." : "Extend by 30 days"}
          </button>
        </div>
      ) : (
        <button
          data-testid="upgrade-checkout-btn"
          onClick={checkout}
          disabled={starting}
          className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {starting ? "Starting..." : `Become a supporter . $${sub?.price_usd?.toFixed(2) || "19.00"}`}
        </button>
      )}
      <p className="font-sans text-xs text-muted-ink mt-4">Pay once. Renews manually whenever you want.</p>
    </div>
  );
}
