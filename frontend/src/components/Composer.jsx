import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

function formatLocal(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d).toLowerCase().replace(" ", "");
  } catch { return ""; }
}

export default function Composer({ onPosted }) {
  const [text, setText] = useState("");
  const [imagePath, setImagePath] = useState("");
  const [uploading, setUploading] = useState(false);
  const [posting, setPosting] = useState(false);
  const [nextWindow, setNextWindow] = useState(null);

  useEffect(() => {
    api.get("/release-window").then((r) => setNextWindow(r.data)).catch(() => {});
  }, []);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "posts");
      const r = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setImagePath(r.data.path);
      toast.success("Image attached");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    if (!text.trim()) return;
    setPosting(true);
    try {
      const r = await api.post("/posts", { text: text.trim(), image_path: imagePath || null });
      setText("");
      setImagePath("");
      toast.success(`Queued for ${formatLocal(r.data.release_at)} CT`);
      onPosted && onPosted();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not post");
    } finally {
      setPosting(false);
    }
  };

  const releaseLabel = nextWindow ? formatLocal(nextWindow.next_release_iso) : "";

  return (
    <section data-testid="composer" className="border hairline rounded-sm p-6 bg-cream">
      <div className="flex items-center justify-between mb-3">
        <p className="uppercase-label">Write</p>
        {releaseLabel && (
          <p className="font-sans text-xs text-muted-ink" data-testid="composer-next-window">
            Releases at <span className="font-semibold ink">{releaseLabel} CT</span>
          </p>
        )}
      </div>
      <textarea
        data-testid="composer-text"
        className="w-full bg-cream border-0 focus:outline-none font-serif text-base sm:text-lg ink leading-relaxed min-h-[110px] resize-none"
        placeholder="Plain words. What did you see today?"
        value={text}
        maxLength={500}
        onChange={(e) => setText(e.target.value)}
      />
      {imagePath && (
        <div className="mt-2 text-xs font-sans text-muted-ink flex items-center gap-2">
          <span>Image attached.</span>
          <button onClick={() => setImagePath("")} data-testid="composer-remove-image" className="underline underline-offset-2 hover:text-gold">remove</button>
        </div>
      )}
      <div className="flex items-center justify-between mt-3 pt-3 border-t hairline">
        <label className="cursor-pointer font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors">
          {uploading ? "Uploading..." : "Attach image"}
          <input data-testid="composer-image-input" type="file" accept="image/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
        </label>
        <div className="flex items-center gap-4">
          <span className="font-sans text-xs text-muted-ink">{text.length}/500</span>
          <button
            data-testid="composer-publish"
            onClick={submit}
            disabled={posting || !text.trim()}
            className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {posting ? "Queueing..." : "Queue for release"}
          </button>
        </div>
      </div>
    </section>
  );
}
