import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Admin-only Brevo bulk-invite tool. Lives inside the Admin page.
 *
 * Two-step flow:
 *  1. Preview: hit /api/admin/invite/preview?list=...  → see who would be invited,
 *     filter out existing members/blacklisted/unsubscribed.
 *  2. Send: hit /api/admin/invite/send with {confirm: "SEND", limit, list_name, dry_run}.
 *
 * For a list this large (~14k contacts) we expose a `limit` so the operator
 * can chunk the send (e.g. 500 at a time) and watch deliverability before
 * blasting the whole list.
 */
export default function AdminInvitePanel() {
  const [listName, setListName] = useState("Your first list");
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [limit, setLimit] = useState(500);
  const [dryRun, setDryRun] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  const loadPreview = async (name) => {
    setLoadingPreview(true);
    setPreview(null);
    try {
      const r = await api.get("/admin/invite/preview", { params: { list: name } });
      setPreview(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Preview failed");
    } finally {
      setLoadingPreview(false);
    }
  };

  useEffect(() => { loadPreview(listName); /* eslint-disable-next-line */ }, []);

  const doSend = async () => {
    if (confirm.trim() !== "SEND") return;
    setBusy(true);
    setLastResult(null);
    try {
      const r = await api.post("/admin/invite/send", {
        confirm: "SEND",
        list_name: listName,
        limit: Number(limit),
        dry_run: dryRun,
      });
      setLastResult(r.data);
      toast.success(
        dryRun
          ? `Dry-run done. Would have sent ${r.data.sent}.`
          : `Sent ${r.data.sent} invites. ${r.data.failed} failed.`
      );
      setConfirm("");
      loadPreview(listName);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally { setBusy(false); }
  };

  const willInvite = preview?.totals?.will_invite || 0;
  const sendable = Math.min(willInvite, Number(limit) || 0);

  return (
    <section data-testid="admin-invite-panel" className="mt-10">
      <p className="uppercase-label mb-3">Brevo bulk invite</p>
      <h2 className="font-display font-semibold text-xl ink mb-2">Invite from a Brevo list</h2>
      <p className="prose-serif text-sm text-muted-ink max-w-prose mb-6">
        Pre-seeds an <code className="font-mono text-xs bg-gold/10 px-1.5 rounded-sm">invited</code> user
        row for every Brevo contact who isn't already a member, then dispatches a personalised invite
        email. When the recipient signs in with Google (matching email) we auto-promote them to
        approved and they skip the application form.
      </p>

      <div className="grid sm:grid-cols-[1fr_auto] gap-3 mb-6">
        <input
          data-testid="admin-invite-list-name"
          value={listName}
          onChange={(e) => setListName(e.target.value)}
          placeholder="Brevo list name"
          className="bg-cream border hairline rounded-sm p-2 font-sans text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
        />
        <button
          type="button"
          onClick={() => loadPreview(listName)}
          disabled={loadingPreview || !listName.trim()}
          data-testid="admin-invite-refresh"
          className="font-sans font-semibold text-sm px-4 py-2 border hairline rounded-sm hover:bg-gold-mid transition-colors disabled:opacity-50"
        >
          {loadingPreview ? "Loading." : "Preview"}
        </button>
      </div>

      {preview && (
        <div data-testid="admin-invite-stats" className="grid sm:grid-cols-2 gap-6 mb-6 bg-cream border hairline rounded-sm p-5">
          <div>
            <p className="uppercase-label mb-2">List</p>
            <p className="font-sans text-sm ink">{preview.list?.name}</p>
            <p className="font-mono text-[11px] text-muted-ink">id {preview.list?.id} · {preview.totals.contacts_in_list} contacts</p>
          </div>
          <div>
            <p className="uppercase-label mb-2">Will invite</p>
            <p className="font-display text-3xl ink leading-none mb-2">{willInvite.toLocaleString()}</p>
            <ul className="font-sans text-xs text-muted-ink space-y-0.5">
              <li>+{preview.totals.contacts_in_list - willInvite} skipped (already a member, blacklisted, or unsubscribed)</li>
              <li className="text-deepred">Existing members: {preview.totals.skipped_already_member}</li>
              <li>Blacklisted: {preview.totals.skipped_blacklisted}</li>
              <li>Unsubscribed: {preview.totals.skipped_unsubscribed}</li>
            </ul>
          </div>
          {preview.candidates?.length > 0 && (
            <div className="sm:col-span-2 pt-4 border-t hairline">
              <p className="uppercase-label mb-2">Sample of who'd get the invite</p>
              <ul className="font-sans text-xs ink/85 space-y-1 max-h-40 overflow-auto pr-2">
                {preview.candidates.slice(0, 12).map((c) => (
                  <li key={c.email} className="flex gap-3">
                    <span className="font-medium min-w-[140px] truncate">{c.name}</span>
                    <span className="text-muted-ink truncate">{c.email}</span>
                  </li>
                ))}
              </ul>
              {preview.sample_only && (
                <p className="font-sans text-[11px] italic text-muted-ink mt-2">
                  (Showing first 12 — full list will be processed at send time.)
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {preview && willInvite > 0 && (
        <div className="border border-gold/40 bg-gold/5 rounded-sm p-5 space-y-4" data-testid="admin-invite-send">
          <div className="grid sm:grid-cols-3 gap-4 items-end">
            <label className="block">
              <span className="uppercase-label block mb-1">Batch size (limit)</span>
              <input
                data-testid="admin-invite-limit"
                type="number"
                min={1}
                max={5000}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                className="w-full bg-cream border hairline rounded-sm p-2 font-mono text-sm ink focus:outline-none focus:ring-1 focus:ring-gold"
              />
              <span className="font-sans text-[11px] text-muted-ink mt-1 block">
                Will actually send: <span className="font-semibold">{sendable.toLocaleString()}</span>
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                data-testid="admin-invite-dry"
                className="rounded-sm"
              />
              <span className="font-sans text-sm ink">Dry-run (no DB writes, no emails)</span>
            </label>
            <div>
              <span className="uppercase-label block mb-1">Type SEND to enable</span>
              <input
                data-testid="admin-invite-confirm"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="SEND"
                className="w-full bg-cream border border-gold rounded-sm p-2 font-mono text-sm ink uppercase tracking-widest focus:outline-none focus:ring-1 focus:ring-gold"
              />
            </div>
          </div>
          <div className="flex items-center gap-3 pt-2">
            <button
              type="button"
              onClick={doSend}
              disabled={confirm.trim() !== "SEND" || busy || sendable === 0}
              data-testid="admin-invite-send-btn"
              className="bg-gold text-cream font-sans font-semibold text-sm px-6 py-2.5 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busy ? "Sending." : dryRun ? `Dry-run ${sendable.toLocaleString()}` : `Send ${sendable.toLocaleString()} invites`}
            </button>
            {sendable > 1000 && (
              <span className="font-sans text-xs text-deepred italic">
                Large batch — consider testing with a smaller limit first.
              </span>
            )}
          </div>
        </div>
      )}

      {lastResult && (
        <div data-testid="admin-invite-result" className="mt-6 border hairline bg-cream rounded-sm p-4">
          <p className="uppercase-label mb-2">Last result</p>
          <ul className="font-sans text-sm ink space-y-1">
            <li>Sent: <strong>{lastResult.sent}</strong></li>
            <li>Failed: {lastResult.failed}</li>
            <li>Skipped (race): {lastResult.skipped_already_member_race}</li>
            <li>Dry run: {lastResult.dry_run ? "yes" : "no"}</li>
          </ul>
        </div>
      )}
    </section>
  );
}
