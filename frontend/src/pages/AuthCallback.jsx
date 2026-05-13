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
    (async () => {
      try {
        const r = await api.post("/auth/session", { session_id });
        // Persist token so Authorization header works even when cookies are blocked
        if (r.data?.session_token) setSessionToken(r.data.session_token);
        // Clear hash
        window.history.replaceState(null, "", window.location.pathname);
        setUser({ ...r.data, has_profile: false });
        if (r.data.status === "approved") {
          // Approved users without profile go to onboarding
          const me = await api.get("/auth/me");
          setUser(me.data);
          if (!me.data.has_profile) {
            navigate("/onboarding", { replace: true, state: { user: me.data } });
          } else {
            navigate("/feed", { replace: true, state: { user: me.data } });
          }
        } else if (r.data.status === "needs_application") {
          navigate("/apply", { replace: true, state: { user: r.data } });
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
