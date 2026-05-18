import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const TIER_LABELS = {
  city: "Cities",
  metro: "Metros",
  state: "States",
  region: "Regions",
  national: "National",
};
const TIER_ORDER = ["city", "metro", "state", "region", "national"];

/**
 * Region picker — chip-style multi-select grouped by tier.
 * Used in both Settings (saves to /api/users/me/regions) and the Write
 * composer (controlled component via `value` + `onChange`).
 *
 * Pass `controlled=true` to use the component without auto-saving.
 */
export default function RegionPicker({
  controlled = false,
  value: controlledValue,
  onChange,
  emptyLabel = "Showing everything — pick regions to filter your feed.",
  testidPrefix = "region",
}) {
  const [grouped, setGrouped] = useState(null);
  const [picks, setPicks] = useState(controlledValue || []);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Keep internal state in sync when controlled
  useEffect(() => {
    if (controlled && Array.isArray(controlledValue)) setPicks(controlledValue);
  }, [controlled, controlledValue]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const tax = await api.get("/regions");
      setGrouped(tax.data?.grouped || {});
      if (!controlled) {
        const me = await api.get("/users/me/regions");
        setPicks(me.data?.regions || []);
      }
    } catch (_e) {
      toast.error("Couldn't load regions.");
    } finally { setLoading(false); }
  }, [controlled]);

  useEffect(() => { load(); }, [load]);

  const toggle = async (slug) => {
    const next = picks.includes(slug)
      ? picks.filter((s) => s !== slug)
      : [...picks, slug].slice(0, 8);
    setPicks(next);
    if (controlled) {
      onChange?.(next);
      return;
    }
    setSaving(true);
    try {
      const r = await api.put("/users/me/regions", { regions: next });
      setPicks(r.data?.regions || next);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't save");
      setPicks(picks); // revert
    } finally { setSaving(false); }
  };

  const clear = async () => {
    setPicks([]);
    if (controlled) {
      onChange?.([]);
      return;
    }
    setSaving(true);
    try {
      await api.put("/users/me/regions", { regions: [] });
      toast.success("Cleared — your feed will show everything.");
    } finally { setSaving(false); }
  };

  if (loading || !grouped) {
    return <p data-testid={`${testidPrefix}-loading`} className="font-serif text-sm text-muted-ink">Loading regions.</p>;
  }

  return (
    <div data-testid={`${testidPrefix}-picker`}>
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <p className="font-serif text-sm text-muted-ink leading-relaxed flex-1 min-w-0">
          {picks.length === 0 ? emptyLabel : (
            <>Showing <strong className="ink/85">{picks.length}</strong> region{picks.length === 1 ? "" : "s"} · up to 8.</>
          )}
        </p>
        {picks.length > 0 && (
          <button
            type="button"
            onClick={clear}
            disabled={saving}
            data-testid={`${testidPrefix}-clear`}
            className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors disabled:opacity-40"
          >
            Clear
          </button>
        )}
      </div>

      <div className="space-y-5">
        {TIER_ORDER.map((tier) => {
          const items = grouped[tier] || [];
          if (items.length === 0) return null;
          return (
            <section key={tier}>
              <p className="font-sans text-[10px] uppercase tracking-[0.22em] font-semibold text-muted-ink mb-2">
                {TIER_LABELS[tier]}
              </p>
              <div className="flex flex-wrap gap-2">
                {items.map((it) => {
                  const on = picks.includes(it.slug);
                  return (
                    <button
                      key={it.slug}
                      type="button"
                      onClick={() => toggle(it.slug)}
                      disabled={saving || (!on && picks.length >= 8)}
                      data-testid={`${testidPrefix}-chip-${it.slug}`}
                      className={`font-sans text-xs font-medium px-3 py-1.5 rounded-full transition-colors ${
                        on
                          ? "bg-gold text-cream"
                          : "border hairline text-muted-ink hover:text-ink hover:border-gold/50"
                      } ${(!on && picks.length >= 8) ? "opacity-40 cursor-not-allowed" : ""}`}
                    >
                      {it.label}
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
