import React, { useEffect, useState } from "react";
import api from "@/lib/api";

function Stat({ label, value, hint }) {
  return (
    <div className="border hairline rounded-sm p-5 bg-cream">
      <div className="uppercase-label mb-1">{label}</div>
      <div className="font-display font-semibold text-3xl ink">{value ?? "."}</div>
      {hint && <div className="font-sans text-xs text-muted-ink mt-2">{hint}</div>}
    </div>
  );
}

export default function AdminAnalyticsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/admin/analytics").then((r) => setData(r.data)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>;
  if (!data) return <div className="font-serif text-base text-muted-ink py-12 text-center">No data.</div>;

  const maxWeek = Math.max(1, ...data.posts_per_week.map((w) => w.count));

  return (
    <div data-testid="admin-analytics" className="space-y-12">
      <section>
        <p className="uppercase-label mb-4">Members</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <Stat label="Approved" value={data.members.total_approved} />
          <Stat label="Active 14d" value={data.members.active_14d} hint="Posted in the last 14 days" />
          <Stat label="With profile" value={data.members.with_profile} />
          <Stat label="Supporters" value={data.members.supporters} />
          <Stat label="Suspended" value={data.members.suspended} />
        </div>
      </section>

      <section>
        <p className="uppercase-label mb-4">Application funnel</p>
        <div className="grid sm:grid-cols-3 gap-4">
          <Stat label="Pending" value={data.application_funnel.pending} />
          <Stat label="Approved" value={data.application_funnel.approved} />
          <Stat label="Declined" value={data.application_funnel.declined} />
        </div>
      </section>

      <section>
        <p className="uppercase-label mb-4">Posts per week</p>
        <div className="border hairline rounded-sm p-6 bg-cream">
          <div className="flex items-end gap-3 h-40">
            {data.posts_per_week.map((w) => {
              const pct = (w.count / maxWeek) * 100;
              return (
                <div key={w.week_start} className="flex flex-col items-center flex-1">
                  <div className="text-xs font-sans font-semibold ink mb-2">{w.count}</div>
                  <div className="w-full bg-gold-mid relative" style={{ height: "100%" }}>
                    <div className="absolute bottom-0 left-0 right-0 bg-gold" style={{ height: `${pct}%` }} />
                  </div>
                  <div className="text-[10px] font-sans text-muted-ink mt-2">{w.week_start.slice(5)}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section>
        <p className="uppercase-label mb-4">Top markets</p>
        {data.top_markets.length === 0 ? (
          <p className="font-serif text-sm text-muted-ink">No markets yet.</p>
        ) : (
          <ul className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            {data.top_markets.map((m) => (
              <li key={m.market} className="px-5 py-3 flex items-center justify-between">
                <span className="font-display font-semibold text-sm ink">{m.market}</span>
                <span className="font-sans text-sm text-muted-ink">{m.count}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="grid sm:grid-cols-2 gap-4">
        <Stat label="Open flags" value={data.open_flags} hint="Pending moderation review" />
        <Stat label="Pete picks (30d)" value={data.pete_picks_30d} />
      </section>
    </div>
  );
}
