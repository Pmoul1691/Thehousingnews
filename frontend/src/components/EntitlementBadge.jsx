import React, { useEffect, useState } from "react";
import api from "@/lib/api";

const PROPERTY_LABELS = {
  ultradianpartners: "Ultradian Partners",
  "ultradia.io": "Ultradia.io",
  ultradia: "Ultradia.io",
};

function formatProperty(p) {
  if (!p) return null;
  const key = String(p).toLowerCase();
  return PROPERTY_LABELS[key] || p;
}

function prettyTier(tier) {
  if (!tier) return "";
  return String(tier).trim().replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric" }).format(d);
  } catch {
    return iso;
  }
}

/**
 * Renders a small "Verified ..." badge with the user's entitlement source.
 * Shows when the user is comped by an upstream property, or when they're a
 * supporter (Stripe), or returns null otherwise. Only fetched for self-profile
 * pages — never for other members' profiles.
 */
export default function EntitlementBadge() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .get("/me/entitlement")
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); });
    return () => { alive = false; };
  }, []);

  if (!data) return null;
  const property = formatProperty(data.property);

  if (data.comped && property) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="entitlement-badge-comped">
        <span className="inline-flex items-center gap-1.5 bg-gold/15 border border-gold/40 text-ink font-sans text-[10px] uppercase tracking-[0.14em] font-semibold px-2.5 py-1 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-gold" aria-hidden />
          Comped via {property}
          {data.tier ? ` · ${prettyTier(data.tier)}` : ""}
        </span>
        {data.renews_at && (
          <span className="font-sans text-xs text-muted-ink" data-testid="entitlement-renews">
            renews {formatDate(data.renews_at)}
          </span>
        )}
      </div>
    );
  }

  if (data.is_supporter) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="entitlement-badge-supporter">
        <span className="inline-flex items-center gap-1.5 bg-gold/15 border border-gold/40 text-ink font-sans text-[10px] uppercase tracking-[0.14em] font-semibold px-2.5 py-1 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-gold" aria-hidden />
          Supporter
        </span>
        {data.supporter_until && (
          <span className="font-sans text-xs text-muted-ink" data-testid="entitlement-supporter-until">
            active through {formatDate(data.supporter_until)}
          </span>
        )}
      </div>
    );
  }

  return null;
}
