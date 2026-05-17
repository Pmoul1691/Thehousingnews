import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const signIn = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + "/auth/callback";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

/**
 * Landing for the one-click "Claim your spot" link in the Brevo bulk invite
 * email. The token in the URL is used only to look up the invitee's email +
 * first name so we can greet them by name. The actual promotion from
 * status=invited → status=approved happens server-side the moment the user
 * signs in with Google using the matching email (see routes/auth.py).
 */
export default function Claim() {
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const token = (search.get("token") || "").trim();
  const [invitee, setInvitee] = useState(null);
  const [error, setError] = useState(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    // If the user is already signed in we don't need the claim page — auth.py
    // has already promoted them to approved (or they're a regular member).
    if (loading) return;
    if (user) {
      navigate(user.has_profile ? "/feed" : "/onboarding", { replace: true });
    }
  }, [user, loading, navigate]);

  useEffect(() => {
    if (!token) {
      setError("Missing invite token.");
      setFetching(false);
      return;
    }
    api
      .get("/auth/invite/lookup", { params: { token } })
      .then((r) => setInvitee(r.data))
      .catch((e) => setError(e?.response?.data?.detail || "Invitation not found"))
      .finally(() => setFetching(false));
  }, [token]);

  if (fetching) {
    return (
      <div className="container-prose py-24 text-center">
        <p className="font-serif italic text-base text-muted-ink">Checking your invitation.</p>
      </div>
    );
  }

  if (error || !invitee) {
    return (
      <div className="container-prose py-24 text-center" data-testid="claim-error">
        <p className="uppercase-label mb-3 text-deepred">Invitation</p>
        <h1 className="font-display font-semibold text-3xl ink mb-4">This link can't be used.</h1>
        <p className="font-serif text-base text-muted-ink leading-relaxed max-w-prose mx-auto mb-8">
          {error || "The invitation token is invalid or has already been claimed."}{" "}
          If you've already signed in, you're all set — head to the feed.
        </p>
        <div className="flex items-center gap-4 justify-center">
          <button
            onClick={signIn}
            data-testid="claim-signin-btn"
            className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-2.5 rounded-full hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
          <Link
            to="/apply"
            className="font-sans text-sm font-medium ink hover:text-gold transition-colors"
          >
            Apply →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container-prose py-24" data-testid="claim-page">
      <p className="uppercase-label mb-4">Invitation</p>
      <h1 className="font-display font-semibold text-4xl sm:text-5xl ink leading-tight mb-6">
        Welcome, {invitee.first_name || "there"}.
      </h1>
      <p className="font-serif text-lg ink/85 leading-relaxed max-w-prose mb-4">
        We&apos;ve held a spot for you in <em>The Housing News</em> — a daily magazine for the real estate industry.
        You&apos;re in for <strong>30 days, free</strong>.
      </p>
      <p className="font-serif text-base text-muted-ink leading-relaxed max-w-prose mb-10">
        Sign in with Google using{" "}
        <span className="font-sans font-semibold ink bg-gold/10 px-1.5 py-0.5 rounded-sm">{invitee.email}</span>{" "}
        and you&apos;re in. No application form, no waiting. After 30 days it&apos;s $12.50/mo or $100/yr — only if you want to stay.
      </p>
      <button
        onClick={signIn}
        data-testid="claim-signin"
        className="inline-flex items-center justify-center bg-gold text-cream font-sans font-semibold text-base px-7 py-3 rounded-full hover:opacity-90 transition-opacity"
      >
        Claim your spot →
      </button>
      <p className="mt-8 font-sans text-xs italic text-muted-ink">
        If you'd rather not, just close this tab. We'll never bother you again.
      </p>
    </div>
  );
}
