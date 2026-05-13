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
  const [emailData, setEmailData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/admin/analytics").then((r) => setData(r.data)),
      api.get("/admin/analytics/email").then((r) => setEmailData(r.data)).catch(() => setEmailData(null)),
    ]).finally(() => setLoading(false));
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

      {emailData && (
        <section data-testid="admin-email-analytics">
          <p className="uppercase-label mb-4">Email engagement (30d)</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
            <Stat label="Sent" value={emailData.totals.sent} />
            <Stat label="Opened" value={emailData.totals.opened} hint={`${emailData.totals.open_rate}%`} />
            <Stat label="Clicked" value={emailData.totals.clicked} hint={`${emailData.totals.click_rate}%`} />
            <Stat label="Open rate" value={`${emailData.totals.open_rate}%`} />
            <Stat label="Click rate" value={`${emailData.totals.click_rate}%`} />
          </div>
          {emailData.items.length === 0 ? (
            <p className="font-serif text-sm text-muted-ink italic">No tracked emails yet. Set APP_PUBLIC_URL and send a digest or essay to populate this.</p>
          ) : (
            <div className="border hairline rounded-sm overflow-x-auto">
              <table className="w-full text-sm" data-testid="email-engagement-table">
                <thead className="bg-[#F5EDD6]">
                  <tr>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Batch</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Sent</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Open</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">Click</th>
                    <th className="text-left p-3 font-sans text-[11px] uppercase tracking-wider text-muted-ink">When</th>
                  </tr>
                </thead>
                <tbody>
                  {emailData.items.map((row, idx) => (
                    <tr key={idx} className="border-t hairline">
                      <td className="p-3 font-display font-semibold text-sm ink"><span className="font-sans text-[10px] uppercase tracking-wider text-gold mr-2">{row.kind}</span>{row.label}</td>
                      <td className="p-3 font-sans text-sm ink">{row.sent}</td>
                      <td className="p-3 font-sans text-sm ink">{row.opened} <span className="text-muted-ink">({row.open_rate}%)</span></td>
                      <td className="p-3 font-sans text-sm ink">{row.clicked} <span className="text-muted-ink">({row.click_rate}%)</span></td>
                      <td className="p-3 font-sans text-xs text-muted-ink">{new Date(row.first_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
