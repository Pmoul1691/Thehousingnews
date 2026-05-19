import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api, { setSessionToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      navigate("/", { replace: true });
      return;
    }
    const session_id = decodeURIComponent(match[1]);
    // Honour an explicit ?next= override (used by /signin to round-trip the user back where they came from).
    const sp = new URLSearchParams(window.location.search);
    const next = sp.get("next");
    (async () => {
      try {
        const r = await api.post("/auth/session", { session_id });
        // Persist token so Authorization header works even when cookies are blocked
        if (r.data?.session_token) setSessionToken(r.data.session_token);
        // Clear hash + query
        window.history.replaceState(null, "", window.location.pathname);
        const me = { ...r.data, has_profile: !!r.data.has_profile };
        setUser(me);
        if (next && next.startsWith("/") && !next.startsWith("//")) {
          navigate(next, { replace: true, state: { user: me } });
          return;
        }
        if (r.data.status === "approved") {
          if (!me.has_profile) {
            navigate("/onboarding", { replace: true, state: { user: me } });
          } else {
            // Approved members land on /news (read-first). The floating
            // Read/Write toggle lets them switch to /feed to compose.
            navigate("/news", { replace: true, state: { user: me } });
          }
        } else if (r.data.status === "needs_application") {
          navigate("/join", { replace: true, state: { user: r.data } });
        } else if (r.data.status === "pending") {
          navigate("/pending", { replace: true, state: { user: r.data } });
        } else if (r.data.status === "declined") {
          navigate("/declined", { replace: true, state: { user: r.data } });
        } else {
          navigate("/", { replace: true });
        }
      } catch (e) {
        navigate("/", { replace: true });
      }
    })();
  }, [navigate, setUser]);

  return (
    <div className="container-prose py-32 text-center">
      <div className="uppercase-label mb-4">Signing you in</div>
      <p className="font-serif text-base text-muted-ink">One moment.</p>
    </div>
  );
}
