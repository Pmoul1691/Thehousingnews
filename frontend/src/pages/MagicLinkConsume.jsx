import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api, { setSessionToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function MagicLinkConsume() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [state, setState] = useState("loading");
  const [err, setErr] = useState("");

  useEffect(() => {
    const token = params.get("token");
    if (!token) { setState("err"); setErr("This link is missing its token."); return; }
    let alive = true;
    api.post("/auth/magic-link/consume", { token })
      .then(async (r) => {
        if (!alive) return;
        // Persist token for cross-origin production where the response
        // cookie is dropped by the browser (withCredentials: false).
        if (r?.data?.session_token) setSessionToken(r.data.session_token);
        await refresh();
        setState("ok");
        setTimeout(() => navigate("/news", { replace: true }), 150);
      })
      .catch((e) => {
        if (!alive) return;
        setErr(e?.response?.data?.detail || "This link is invalid or has expired.");
        setState("err");
      });
    return () => { alive = false; };
  }, [params, navigate, refresh]);

  return (
    <div className="container-prose py-24 text-center animate-fade-up">
      {state === "loading" && (
        <>
          <p className="uppercase-label mb-3">Signing you in</p>
          <h1 className="font-display font-semibold text-2xl ink">One sec…</h1>
        </>
      )}
      {state === "ok" && (
        <div data-testid="magic-ok">
          <p className="uppercase-label mb-3">Signed in</p>
          <h1 className="font-display font-semibold text-3xl ink">You're in.</h1>
        </div>
      )}
      {state === "err" && (
        <div data-testid="magic-err">
          <p className="uppercase-label mb-3 text-deepred">Link expired</p>
          <h1 className="font-display font-semibold text-3xl ink mb-4">That sign-in link won't work.</h1>
          <p className="font-serif text-base text-muted-ink max-w-prose mx-auto mb-6">{err}</p>
          <Link
            to="/signin"
            className="font-sans text-sm font-semibold text-gold hover:opacity-80 underline underline-offset-4 decoration-gold-mid"
          >
            Request a new link →
          </Link>
        </div>
      )}
    </div>
  );
}
