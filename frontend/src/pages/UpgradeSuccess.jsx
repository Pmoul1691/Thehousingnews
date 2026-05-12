import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import BloomMark from "@/components/BloomMark";
import { toast } from "sonner";

export default function UpgradeSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const navigate = useNavigate();
  const [status, setStatus] = useState({ payment_status: "pending" });
  const [attempts, setAttempts] = useState(0);
  const timer = useRef(null);

  useEffect(() => {
    if (!sessionId) { navigate("/upgrade", { replace: true }); return; }
    let cancelled = false;

    const poll = async (n) => {
      if (n > 8 || cancelled) return;
      try {
        const r = await api.get(`/payments/status/${sessionId}`);
        if (cancelled) return;
        setStatus(r.data);
        if (r.data.payment_status === "paid") {
          toast.success("Welcome, supporter.");
          return;
        }
        if (r.data.status === "expired") {
          toast.error("Checkout expired");
          return;
        }
        setAttempts(n + 1);
        timer.current = setTimeout(() => poll(n + 1), 2000);
      } catch (e) {
        if (!cancelled) toast.error("Could not check status");
      }
    };
    poll(0);
    return () => { cancelled = true; if (timer.current) clearTimeout(timer.current); };
  }, [sessionId, navigate]);

  const paid = status.payment_status === "paid";

  return (
    <div className="container-prose py-24 text-center animate-fade-up">
      <div className="flex justify-center mb-8"><BloomMark size={72} /></div>
      <p className="uppercase-label mb-3">Checkout</p>
      {paid ? (
        <>
          <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6" data-testid="paid-headline">Thank you.</h1>
          <p className="font-serif text-lg leading-relaxed ink/80 max-w-prose mx-auto">You are now a supporter. The small Bloom mark next to your name is on. Talk to you at the next release window.</p>
          <Link to="/feed" data-testid="paid-feed-link" className="inline-block mt-10 font-sans text-sm font-semibold ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">Back to the feed</Link>
        </>
      ) : (
        <>
          <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">Almost done.</h1>
          <p className="font-serif text-lg leading-relaxed ink/80 max-w-prose mx-auto">Checking your payment. This usually takes a few seconds.</p>
          <div className="mt-8 font-sans text-xs text-muted-ink" data-testid="paid-status">Status: {status.payment_status} ({attempts}/8)</div>
        </>
      )}
    </div>
  );
}
