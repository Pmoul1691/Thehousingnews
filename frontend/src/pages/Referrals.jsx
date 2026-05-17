import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import PageMeta from "@/components/PageMeta";

/**
 * /referrals — Member referrals page.
 *
 * Surfaces three things, all derived from existing invite_codes + users rows:
 *
 *   1. The Top Connectors leaderboard (public-to-members; the top 10 members
 *      ranked by approved-referral count).
 *   2. My referral stats (issued / redeemed / approved + badge progress).
 *   3. A list of people I invited, with their current status.
 *
 * The "incentive" is intentionally non-monetary — earning the badge and
 * a leaderboard spot. Three approved invites earns the Top Connector
 * status; the threshold is read from /api/referrals/me.threshold.
 */
function MemberAvatar({ name, avatarPath, size = 40 }) {
  const initials = (name || "M")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  if (avatarPath) {
    const src = avatarPath.startsWith("http") ? avatarPath : `${process.env.REACT_APP_BACKEND_URL}${avatarPath}`;
    return (
      <img
        src={src}
        alt={name}
        width={size}
        height={size}
        style={{ width: size, height: size }}
        className="rounded-full object-cover border border-gold/30 shrink-0"
      />
    );
  }
  return (
    <div
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      className="rounded-full bg-gold/15 text-gold font-display font-semibold flex items-center justify-center shrink-0"
    >
      {initials}
    </div>
  );
}

export default function Referrals() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [me, setMe] = useState(null);
  const [board, setBoard] = useState({ items: [], threshold: 3 });
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    Promise.all([
      api.get("/referrals/me").catch(() => ({ data: null })),
      api.get("/referrals/leaderboard").catch(() => ({ data: { items: [], threshold: 3 } })),
    ]).then(([m, b]) => {
      setMe(m.data);
      setBoard(b.data);
    }).finally(() => setFetching(false));
  }, [user, loading, navigate]);

  if (loading || fetching) {
    return <div className="container-narrow py-24 font-serif text-center text-muted-ink">Loading.</div>;
  }
  if (!me) {
    return <div className="container-narrow py-24 font-serif text-center text-muted-ink">Could not load referrals.</div>;
  }

  const threshold = me.threshold || 3;
  const progress = Math.min(1, me.approved / threshold);
  const remainingToBadge = Math.max(0, threshold - me.approved);

  return (
    <div className="container-narrow py-12 sm:py-16" data-testid="referrals-page">
      <PageMeta title="Top Connectors · The Housing News" description="Earn the Top Connector badge by bringing in three approved members." />

      <header className="mb-10">
        <p className="uppercase-label mb-2">Referrals</p>
        <h1 className="font-display font-semibold text-4xl sm:text-5xl ink mb-3">Top Connectors.</h1>
        <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose">
          The network grows when members vouch for the right people. Three approved invites earns you the <strong className="text-gold">Top Connector</strong> badge — it shows on your profile, on every directory card, and on the public leaderboard below.
        </p>
      </header>

      {/* My stats ------------------------------------------------------- */}
      <section className="mb-12" data-testid="referrals-my-stats">
        <p className="uppercase-label mb-4">Your progress</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <Stat label="Codes left" value={`${me.remaining} / 20`} testid="my-remaining" />
          <Stat label="Sent" value={me.issued} />
          <Stat label="Redeemed" value={me.redeemed} />
          <Stat
            label="Approved"
            value={me.approved}
            accent
            badge={me.is_top_connector ? "Top Connector" : null}
            testid="my-approved"
          />
        </div>

        {/* Progress to badge */}
        {!me.is_top_connector && (
          <div className="border hairline rounded-sm bg-cream p-5" data-testid="badge-progress">
            <div className="flex items-baseline justify-between gap-3 mb-3">
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold">Badge progress</p>
              <p className="font-serif text-sm ink/80">
                {remainingToBadge === 1
                  ? "One more approved invite earns the badge."
                  : `${remainingToBadge} more approved invites to earn the badge.`}
              </p>
            </div>
            <div className="h-1.5 bg-[#E8D4A0]/40 rounded-sm overflow-hidden">
              <div
                className="h-full bg-gold transition-all"
                style={{ width: `${progress * 100}%` }}
                data-testid="badge-progress-bar"
              />
            </div>
          </div>
        )}
        {me.is_top_connector && (
          <div className="border-2 border-gold rounded-sm bg-[#FBF6E8] p-5" data-testid="top-connector-confirm">
            <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold">You earned it.</p>
            <p className="font-display font-semibold text-xl ink mt-1">Top Connector.</p>
            <p className="font-serif text-sm ink/80 mt-1">Your badge is live on your profile and on every directory card. Thank you for building the room.</p>
          </div>
        )}

        <div className="mt-5">
          <Link
            to="/settings"
            data-testid="referrals-manage-codes"
            className="font-sans text-xs uppercase tracking-[0.18em] font-semibold text-gold hover:text-ink transition-colors"
          >
            Manage your codes in Settings &rarr;
          </Link>
        </div>
      </section>

      {/* Invitees ------------------------------------------------------- */}
      {me.invitees.length > 0 && (
        <section className="mb-12" data-testid="referrals-invitees">
          <p className="uppercase-label mb-4">People you brought in</p>
          <ul className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            {me.invitees.map((it) => (
              <li
                key={it.code}
                data-testid={`invitee-${it.code}`}
                className="px-5 py-4 flex items-baseline justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="font-display font-semibold text-base ink">{it.name}</div>
                  <div className="font-mono text-[11px] text-muted-ink mt-0.5 tracking-wider">{it.code}</div>
                </div>
                <span
                  className={`font-sans text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm font-semibold ${
                    it.status === "approved"
                      ? "bg-gold text-cream"
                      : it.status === "pending"
                      ? "bg-cream text-gold border border-gold-mid"
                      : "bg-cream text-muted-ink border hairline"
                  }`}
                >
                  {it.status}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Leaderboard ---------------------------------------------------- */}
      <section data-testid="referrals-leaderboard">
        <p className="uppercase-label mb-4">The leaderboard</p>
        {board.items.length === 0 ? (
          <div className="border hairline rounded-sm bg-cream p-6 text-center">
            <p className="font-serif italic text-base text-muted-ink">No one has earned the Top Connector badge yet.</p>
            <p className="font-serif text-sm ink/70 mt-2">Be the first. Three approved invites is all it takes.</p>
          </div>
        ) : (
          <ol className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="leaderboard-list">
            {board.items.map((m, i) => (
              <li
                key={m.user_id}
                data-testid={`leaderboard-row-${i + 1}`}
                className={`px-5 py-4 flex items-center gap-4 ${m.user_id === user.user_id ? "bg-[#FBF6E8]" : ""}`}
              >
                <span className="font-display font-semibold text-lg text-gold w-8 shrink-0">{i + 1}</span>
                <MemberAvatar name={m.name} avatarPath={m.avatar_path} size={40} />
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/profile/${m.user_id}`}
                    className="font-display font-semibold text-base ink hover:text-gold transition-colors truncate flex items-center gap-2"
                  >
                    {m.name}
                    {m.is_top_connector && (
                      <span className="font-sans text-[9px] uppercase tracking-wider bg-gold text-cream px-1.5 py-0.5 rounded-sm font-semibold">
                        Top Connector
                      </span>
                    )}
                  </Link>
                  {m.market && <div className="font-serif italic text-xs text-muted-ink mt-0.5 truncate">{m.market}</div>}
                </div>
                <div className="text-right shrink-0">
                  <div className="font-display font-semibold text-xl ink">{m.approved}</div>
                  <div className="font-sans text-[10px] uppercase tracking-wider text-muted-ink">approved</div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, accent = false, badge = null, testid }) {
  return (
    <div className={`border hairline rounded-sm p-4 ${accent ? "bg-[#FBF6E8]" : "bg-cream"}`} data-testid={testid}>
      <div className={`font-sans text-[10px] uppercase tracking-[0.18em] font-semibold ${accent ? "text-gold" : "text-muted-ink"}`}>{label}</div>
      <div className="font-display font-semibold text-2xl ink mt-1 flex items-center gap-2 flex-wrap">
        {value}
        {badge && (
          <span data-testid="top-connector-badge-mine" className="font-sans text-[9px] uppercase tracking-wider bg-gold text-cream px-1.5 py-0.5 rounded-sm font-semibold">
            {badge}
          </span>
        )}
      </div>
    </div>
  );
}
