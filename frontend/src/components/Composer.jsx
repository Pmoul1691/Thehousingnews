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
  const [mode, setMode] = useState("post"); // post | essay
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
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

  const reset = () => {
    setText(""); setTitle(""); setSubtitle(""); setImagePath("");
  };

  const submit = async () => {
    if (!text.trim()) return;
    if (mode === "essay" && !title.trim()) { toast.error("Essays need a title"); return; }
    if (mode === "essay" && text.trim().length < 100) { toast.error("Essays need at least 100 characters"); return; }
    setPosting(true);
    try {
      const r = await api.post("/posts", {
        kind: mode,
        text: text.trim(),
        title: mode === "essay" ? title.trim() : null,
        subtitle: mode === "essay" ? (subtitle.trim() || null) : null,
        image_path: imagePath || null,
      });
      if (mode === "essay") {
        toast.success("Essay published. Emails are going out now.");
      } else {
        toast.success(`Queued for ${formatLocal(r.data.release_at)} CT`);
      }
      reset();
      onPosted && onPosted();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not publish");
    } finally {
      setPosting(false);
    }
  };

  const releaseLabel = nextWindow ? formatLocal(nextWindow.next_release_iso) : "";
  const isEssay = mode === "essay";

  return (
    <section data-testid="composer" className="border hairline rounded-sm p-6 bg-cream">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div className="flex items-center gap-1 border hairline rounded-sm p-0.5" data-testid="composer-mode-toggle">
          <button
            data-testid="composer-mode-post"
            onClick={() => setMode("post")}
            className={`px-3 py-1.5 font-sans text-xs font-semibold uppercase tracking-wider transition-colors ${mode === "post" ? "bg-gold text-cream" : "text-muted-ink hover:text-ink"}`}
          >
            Short post
          </button>
          <button
            data-testid="composer-mode-essay"
            onClick={() => setMode("essay")}
            className={`px-3 py-1.5 font-sans text-xs font-semibold uppercase tracking-wider transition-colors ${mode === "essay" ? "bg-gold text-cream" : "text-muted-ink hover:text-ink"}`}
          >
            Essay
          </button>
        </div>
        <p className="font-sans text-xs text-muted-ink" data-testid="composer-release-note">
          {isEssay ? (
            <>Publishes <span className="font-semibold ink">now</span>. Emails your followers.</>
          ) : (
            releaseLabel ? (<>Releases at <span className="font-semibold ink">{releaseLabel} CT</span></>) : null
          )}
        </p>
      </div>

      {isEssay && (
        <div className="mb-3 space-y-2 border-b hairline pb-4">
          <input
            data-testid="composer-title"
            placeholder="Title"
            value={title}
            maxLength={160}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-cream border-0 focus:outline-none font-display font-semibold text-2xl ink placeholder:text-[#2C2410]/30"
          />
          <input
            data-testid="composer-subtitle"
            placeholder="Subtitle (optional)"
            value={subtitle}
            maxLength={240}
            onChange={(e) => setSubtitle(e.target.value)}
            className="w-full bg-cream border-0 focus:outline-none font-serif italic text-base ink placeholder:text-[#2C2410]/30"
          />
        </div>
      )}

      <textarea
        data-testid="composer-text"
        className={`w-full bg-cream border-0 focus:outline-none font-serif text-base sm:text-lg ink leading-relaxed resize-none ${isEssay ? "min-h-[320px]" : "min-h-[110px]"}`}
        placeholder={isEssay ? "Write the essay. Plain words, real specifics, line breaks fine." : "Plain words. What did you see today?"}
        value={text}
        maxLength={isEssay ? 50000 : 500}
        onChange={(e) => setText(e.target.value)}
      />
      {imagePath && (
        <div className="mt-2 text-xs font-sans text-muted-ink flex items-center gap-2">
          <span>{isEssay ? "Cover image attached." : "Image attached."}</span>
          <button onClick={() => setImagePath("")} data-testid="composer-remove-image" className="underline underline-offset-2 hover:text-gold">remove</button>
        </div>
      )}
      <div className="flex items-center justify-between mt-3 pt-3 border-t hairline">
        <label className="cursor-pointer font-sans text-sm font-medium text-muted-ink hover:text-gold transition-colors">
          {uploading ? "Uploading..." : isEssay ? "Add cover image" : "Attach image"}
          <input data-testid="composer-image-input" type="file" accept="image/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
        </label>
        <div className="flex items-center gap-4">
          <span className="font-sans text-xs text-muted-ink">{text.length}/{isEssay ? "50000" : "500"}</span>
          <button
            data-testid="composer-publish"
            onClick={submit}
            disabled={posting || !text.trim() || (isEssay && !title.trim())}
            className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {posting ? (isEssay ? "Publishing..." : "Queueing...") : (isEssay ? "Publish essay" : "Queue for release")}
          </button>
        </div>
      </div>
    </section>
  );
}
