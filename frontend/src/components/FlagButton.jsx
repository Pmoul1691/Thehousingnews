import React, { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Tiny inline flag button. Used on PostItem and Reply.
 * targetKind: 'post' | 'reply'
 */
export default function FlagButton({ targetKind, targetId, viewerFlagged, isOwner, onFlagged }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isOwner) return null;

  const submit = async () => {
    setSubmitting(true);
    try {
      const url = targetKind === "post" ? `/posts/${targetId}/flag` : `/replies/${targetId}/flag`;
      await api.post(url, { reason: reason.trim() || null });
      toast.success("Flagged. Pete will take a look.");
      setOpen(false);
      setReason("");
      onFlagged && onFlagged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not flag");
    } finally {
      setSubmitting(false);
    }
  };

  if (viewerFlagged) {
    return <span data-testid={`flag-done-${targetId}`} className="font-sans text-xs text-muted-ink italic">Reported</span>;
  }

  return (
    <div className="relative">
      <button
        data-testid={`flag-${targetKind}-${targetId}`}
        onClick={() => setOpen((v) => !v)}
        className="font-sans text-xs text-muted-ink hover:text-deepred transition-colors"
      >
        Report
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 border hairline rounded-sm bg-cream p-3 shadow-sm z-20">
          <p className="font-sans text-xs text-muted-ink mb-2">Tell Pete what is off, briefly. Optional.</p>
          <textarea
            data-testid={`flag-reason-${targetId}`}
            value={reason}
            maxLength={300}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Spam, off-topic, hostile, etc."
            className="w-full bg-cream border hairline rounded-sm p-2 font-sans text-xs ink focus:outline-none focus:ring-1 focus:ring-gold"
            rows={2}
          />
          <div className="flex items-center justify-end gap-2 mt-2">
            <button onClick={() => setOpen(false)} className="font-sans text-xs text-muted-ink hover:text-ink">Cancel</button>
            <button
              data-testid={`flag-submit-${targetId}`}
              onClick={submit}
              disabled={submitting}
              className="bg-deepred text-cream font-sans font-semibold text-xs px-3 py-1.5 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {submitting ? "Sending..." : "Send report"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
