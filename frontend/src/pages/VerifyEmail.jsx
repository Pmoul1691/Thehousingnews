import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [state, setState] = useState("loading"); // loading | ok | err
  const [err, setErr] = useState("");

  useEffect(() => {
    const token = params.get("token");
    if (!token) { setState("err"); setErr("This link is missing its token."); return; }
    let alive = true;
    api.post("/auth/email/verify", { token })
      .then(async () => {
        if (!alive) return;
        await refresh();
        setState("ok");
        setTimeout(() => navigate("/feed", { replace: true }), 1500);
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
          <p className="uppercase-label mb-3">Verifying</p>
          <h1 className="font-display font-semibold text-2xl ink">Hold on a second…</h1>
        </>
      )}
      {state === "ok" && (
        <div data-testid="verify-ok">
          <p className="uppercase-label mb-3">Verified</p>
          <h1 className="font-display font-semibold text-3xl ink mb-4">Email confirmed.</h1>
          <p className="font-serif text-base text-muted-ink">Sending you to your feed.</p>
        </div>
      )}
      {state === "err" && (
        <div data-testid="verify-err">
          <p className="uppercase-label mb-3 text-deepred">Couldn't verify</p>
          <h1 className="font-display font-semibold text-3xl ink mb-4">This link won't work.</h1>
          <p className="font-serif text-base text-muted-ink max-w-prose mx-auto mb-6">{err}</p>
          <Link
            to="/signin"
            className="font-sans text-sm font-semibold text-gold hover:opacity-80 underline underline-offset-4 decoration-gold-mid"
          >
            Try signing in again →
          </Link>
        </div>
      )}
    </div>
  );
}
