import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (password.length < 8) { toast.error("Password must be at least 8 characters."); return; }
    if (password !== confirm) { toast.error("Passwords don't match."); return; }
    if (!token) { toast.error("Reset link is missing its token."); return; }
    setBusy(true);
    try {
      await api.post("/auth/password/reset/confirm", { token, password });
      toast.success("Password updated. Sign in with your new password.");
      navigate("/signin?mode=password", { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "This link is invalid or has expired.");
    } finally { setBusy(false); }
  };

  return (
    <div className="container-prose py-20 animate-fade-up">
      <p className="uppercase-label mb-3">Reset password</p>
      <h1 className="font-display font-semibold text-3xl ink mb-6">Pick a new one.</h1>
      <form onSubmit={submit} className="space-y-4 max-w-md" data-testid="reset-form">
        <div>
          <label className="block uppercase-label mb-2">New password</label>
          <input
            data-testid="reset-pw"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
          />
        </div>
        <div>
          <label className="block uppercase-label mb-2">Confirm password</label>
          <input
            data-testid="reset-pw-confirm"
            type="password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full bg-cream border hairline rounded-sm p-3 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
          />
        </div>
        <div className="flex items-center gap-4 pt-2">
          <button
            type="submit"
            disabled={busy || password.length < 8 || password !== confirm}
            data-testid="reset-submit"
            className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-3 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? "Updating…" : "Update password"}
          </button>
          <Link
            to="/signin"
            className="font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
