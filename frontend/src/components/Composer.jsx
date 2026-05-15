import React, { useEffect, useRef, useState } from "react";
import api, { API } from "@/lib/api";
import { toast } from "sonner";
import RichTextEditor from "@/components/RichTextEditor";

function formatLocal(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const opts = { hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" };
    return new Intl.DateTimeFormat("en-US", opts).format(d).toLowerCase().replace(" ", "");
  } catch { return ""; }
}

function toLocalInput(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch { return ""; }
}

const MAX_IMAGES = 4;

export default function Composer({ onPosted }) {
  const [mode, setMode] = useState("post");
  const [editorMode, setEditorMode] = useState(() => localStorage.getItem("essay_editor_mode") || "visual");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [media, setMedia] = useState([]); // {kind, path, mime, thumbnail_path, duration_s, width, height, provider, video_id, embed_url}
  const [embedUrl, setEmbedUrl] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [uploading, setUploading] = useState("");
  const [posting, setPosting] = useState(false);
  const [nextWindow, setNextWindow] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [currentPrompt, setCurrentPrompt] = useState(null);
  const [linkPrompt, setLinkPrompt] = useState(false);
  const draftDirty = useRef(false);

  const images = media.filter((m) => m.kind === "image");
  const video = media.find((m) => m.kind === "video");
  const audio = media.find((m) => m.kind === "audio");
  const embed = media.find((m) => m.kind === "embed");

  useEffect(() => {
    api.get("/drafts/mine").then((r) => {
      if (r.data && r.data.user_id) {
        setMode(r.data.kind || "post");
        setText(r.data.text || "");
        setTitle(r.data.title || "");
        setSubtitle(r.data.subtitle || "");
        const m = r.data.media || (r.data.image_path ? [{ kind: "image", path: r.data.image_path }] : []);
        setMedia(m);
        setScheduledAt(r.data.scheduled_at ? toLocalInput(r.data.scheduled_at) : "");
      }
    }).catch(() => {}).finally(() => setDraftLoaded(true));
    api.get("/release-window").then((r) => setNextWindow(r.data)).catch(() => {});
    api.get("/prompts/current").then((r) => {
      if (r.data && r.data.prompt_id) setCurrentPrompt(r.data);
    }).catch(() => {});
  }, []);

  // Auto-save every 5s when dirty
  useEffect(() => {
    if (!draftLoaded) return;
    draftDirty.current = true;
    const t = setTimeout(async () => {
      if (!draftDirty.current) return;
      if (!text && !title && !subtitle && media.length === 0) return;
      try {
        const scheduledIso = scheduledAt ? new Date(scheduledAt).toISOString() : null;
        await api.put("/drafts/mine", {
          kind: mode,
          text,
          title: title || null,
          subtitle: subtitle || null,
          image_path: images[0]?.path || null,
          media,
          scheduled_at: scheduledIso,
        });
        setSavedAt(new Date());
        draftDirty.current = false;
      } catch (_e) { /* silent */ }
    }, 5000);
    return () => clearTimeout(t);
  }, [text, title, subtitle, media, mode, scheduledAt, draftLoaded, images]);

  const uploadFile = async (file, label) => {
    if (!file) return;
    setUploading(label);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "posts");
      const r = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      return r.data; // {path, content_type, size, media_kind, thumbnail_path?, duration_s?, width?, height?}
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
      return null;
    } finally { setUploading(""); }
  };

  const onImageInput = async (files) => {
    if (!files || files.length === 0) return;
    const space = MAX_IMAGES - images.length;
    if (space <= 0) { toast.error(`Max ${MAX_IMAGES} images`); return; }
    const picked = Array.from(files).slice(0, space);
    for (const f of picked) {
      const r = await uploadFile(f, `image ${picked.indexOf(f) + 1}`);
      if (r) {
        setMedia((arr) => [...arr, { kind: "image", path: r.path, mime: r.content_type }]);
      }
    }
    toast.success(picked.length === 1 ? "Image attached" : `${picked.length} images attached`);
  };

  const onVideoInput = async (file) => {
    if (!file) return;
    if (video) { toast.error("Only one video per post"); return; }
    if (embed) { toast.error("Remove the video URL first"); return; }
    const r = await uploadFile(file, "video");
    if (!r) return;
    // Short videos: ready immediately
    if (!r.processing) {
      setMedia((arr) => [...arr, {
        kind: "video", path: r.path, mime: r.content_type,
        thumbnail_path: r.thumbnail_path || null,
        duration_s: r.duration_s, width: r.width, height: r.height,
      }]);
      toast.success("Video attached");
      return;
    }
    // Long videos: queue a placeholder, poll the transcode job until ready
    const jobId = r.transcode_job_id;
    const placeholder = {
      kind: "video",
      processing: true,
      transcode_job_id: jobId,
      duration_s: r.duration_s,
      width: r.width,
      height: r.height,
    };
    setMedia((arr) => [...arr, placeholder]);
    toast.success("Video uploaded. Transcoding for smooth playback.");

    const pollMs = 4000;
    const maxTries = 90; // ~6 minutes
    let tries = 0;
    const poll = async () => {
      tries += 1;
      try {
        const s = await api.get(`/uploads/transcode/${jobId}`);
        if (s.data.status === "ready") {
          setMedia((arr) => arr.map((m) => m.transcode_job_id === jobId ? {
            kind: "video",
            hls_path: s.data.hls_path,
            thumbnail_path: s.data.thumbnail_path || null,
            duration_s: s.data.duration_s,
            width: s.data.width,
            height: s.data.height,
          } : m));
          toast.success("Video ready");
          return;
        }
        if (s.data.status === "failed") {
          setMedia((arr) => arr.filter((m) => m.transcode_job_id !== jobId));
          toast.error(`Transcode failed: ${s.data.error || "unknown"}`);
          return;
        }
        if (tries < maxTries) setTimeout(poll, pollMs);
      } catch (e) {
        if (tries < maxTries) setTimeout(poll, pollMs);
      }
    };
    setTimeout(poll, pollMs);
  };

  const onAudioInput = async (file) => {
    if (!file) return;
    if (audio) { toast.error("Only one audio per post"); return; }
    const r = await uploadFile(file, "audio");
    if (r) {
      setMedia((arr) => [...arr, { kind: "audio", path: r.path, mime: r.content_type, duration_s: r.duration_s, peaks: r.peaks || [] }]);
      toast.success("Audio attached");
    }
  };

  const attachEmbed = async () => {
    const url = embedUrl.trim();
    if (!url) return;
    if (embed) { toast.error("Only one URL embed"); return; }
    if (video) { toast.error("Remove the uploaded video first"); return; }
    try {
      const r = await api.post("/uploads/embed", { url });
      setMedia((arr) => [...arr, {
        kind: "embed",
        provider: r.data.provider,
        video_id: r.data.video_id,
        embed_url: r.data.embed_url,
        thumbnail_url: r.data.thumbnail_url || null,
      }]);
      setEmbedUrl("");
      toast.success(`${r.data.provider} video attached`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not parse URL");
    }
  };

  const removeMedia = (idx) => {
    setMedia((arr) => arr.filter((_, i) => i !== idx));
  };

  const moveMedia = (idx, delta) => {
    setMedia((arr) => {
      const next = [...arr];
      const target = idx + delta;
      if (target < 0 || target >= next.length) return arr;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const reset = async () => {
    setText(""); setTitle(""); setSubtitle(""); setMedia([]); setEmbedUrl(""); setScheduledAt("");
    try { await api.delete("/drafts/mine"); } catch (_e) {}
    setSavedAt(null);
  };

  const submit = async () => {
    if (!text.trim() && media.length === 0) return;
    if (mode === "essay" && !title.trim()) { toast.error("Essays need a title"); return; }
    if (mode === "essay" && text.trim().length < 100) { toast.error("Essays need at least 100 characters"); return; }
    const scheduledIso = mode === "essay" && scheduledAt ? new Date(scheduledAt).toISOString() : null;
    if (scheduledIso && new Date(scheduledIso) <= new Date()) {
      toast.error("Schedule must be in the future");
      return;
    }
    setPosting(true);
    try {
      const cleanMedia = media.map((m) => {
        const next = { ...m };
        delete next.processing;
        delete next.transcode_job_id;
        return next;
      });
      const r = await api.post("/posts", {
        kind: mode,
        text: text.trim() || ".",
        title: mode === "essay" ? title.trim() : null,
        subtitle: mode === "essay" ? (subtitle.trim() || null) : null,
        image_path: images[0]?.path || null,
        media: cleanMedia,
        scheduled_at: scheduledIso,
        prompt_id: linkPrompt && currentPrompt ? currentPrompt.prompt_id : null,
      });
      if (mode === "essay") {
        if (r.data.status === "scheduled") toast.success("Essay scheduled");
        else toast.success("Essay published. Emails are going out now.");
      } else {
        toast.success(`Queued for ${formatLocal(r.data.release_at)} CT`);
      }
      await reset();
      onPosted && onPosted();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not publish");
    } finally { setPosting(false); }
  };

  const releaseLabel = nextWindow ? formatLocal(nextWindow.next_release_iso) : "";
  const isEssay = mode === "essay";
  const savedLabel = savedAt ? `Draft saved at ${savedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "";

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
            scheduledAt ? (<>Publishes <span className="font-semibold ink">{new Date(scheduledAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span></>)
              : (<>Publishes <span className="font-semibold ink">now</span>. Emails your followers.</>)
          ) : (
            releaseLabel ? (<>Releases at <span className="font-semibold ink">{releaseLabel} CT</span></>) : null
          )}
        </p>
      </div>

      {isEssay && (
        <div className="mb-3 space-y-2 border-b hairline pb-4">
          <input data-testid="composer-title" placeholder="Title" value={title} maxLength={160}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-cream border-0 focus:outline-none font-display font-semibold text-2xl ink placeholder:text-[#2C2410]/30" />
          <input data-testid="composer-subtitle" placeholder="Subtitle (optional)" value={subtitle} maxLength={240}
            onChange={(e) => setSubtitle(e.target.value)}
            className="w-full bg-cream border-0 focus:outline-none font-serif italic text-base ink placeholder:text-[#2C2410]/30" />
        </div>
      )}

      {isEssay && (
        <div className="flex items-center gap-1 mb-2 border hairline rounded-sm p-0.5 w-fit" data-testid="essay-editor-toggle">
          {[{ k: "visual", l: "Visual" }, { k: "markdown", l: "Markdown" }].map((t) => (
            <button
              key={t.k}
              type="button"
              data-testid={`essay-editor-${t.k}`}
              onClick={() => { setEditorMode(t.k); localStorage.setItem("essay_editor_mode", t.k); }}
              className={`px-3 py-1 font-sans text-[11px] font-semibold uppercase tracking-wider transition-colors ${editorMode === t.k ? "bg-gold text-cream" : "text-muted-ink hover:text-ink"}`}
            >
              {t.l}
            </button>
          ))}
        </div>
      )}

      {isEssay && editorMode === "visual" ? (
        <RichTextEditor
          value={text}
          onChange={setText}
          placeholder="Write the essay. Type / to insert headings, images, video, audio, or links."
        />
      ) : (
        <textarea
          data-testid="composer-text"
          className={`w-full bg-cream border-0 focus:outline-none font-serif text-base sm:text-lg ink leading-relaxed resize-none ${isEssay ? "min-h-[340px]" : "min-h-[110px]"}`}
          placeholder={isEssay ? "Write the essay. Markdown is supported: **bold**, _italic_, # heading, - lists, > quotes, [link](url)." : "Plain words. What happened on a deal today?"}
          value={text}
          maxLength={isEssay ? 50000 : 500}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      <p className="mt-1 font-sans text-[11px] text-muted-ink/80" data-testid="composer-tag-hint">
        Tip: type <code className="font-mono text-gold">#chicago</code> or <code className="font-mono text-gold">#pricing</code> to tag this post. Other members can browse by tag.
      </p>
      {/* Media previews */}
      {media.length > 0 && (
        <div className="mt-4 space-y-2" data-testid="composer-media-list">
          {media.map((m, idx) => {
            const label =
              m.kind === "image" ? `Image . ${(m.path || "").split("/").pop()}` :
              m.kind === "video" ? (m.processing ? `Video . transcoding...` : `Video . ${m.duration_s ? `${Math.round(m.duration_s)}s` : "uploaded"}`) :
              m.kind === "audio" ? `Audio . ${m.duration_s ? `${Math.round(m.duration_s)}s` : "uploaded"}` :
              m.kind === "embed" ? `${m.provider} video . ${m.video_id}` : "Media";
            return (
              <div key={idx} data-testid={`composer-media-${idx}`} className="flex items-center justify-between gap-3 px-3 py-2 border hairline rounded-sm bg-cream">
                <div className="flex items-center gap-3 min-w-0">
                  {m.kind === "image" && m.path && (
                    <img src={`${API}/uploads/file/${m.path}`} alt="" className="w-10 h-10 object-cover border hairline rounded-sm" />
                  )}
                  {(m.kind === "video" && m.thumbnail_path) && (
                    <img src={`${API}/uploads/file/${m.thumbnail_path}`} alt="" className="w-10 h-10 object-cover border hairline rounded-sm" />
                  )}
                  <span className="font-sans text-xs ink truncate">{label}</span>
                </div>
                <div className="flex items-center gap-1">
                  {m.kind === "image" && (
                    <>
                      <button
                        data-testid={`composer-media-up-${idx}`}
                        onClick={() => moveMedia(idx, -1)}
                        disabled={idx === 0 || media.slice(0, idx).every((x) => x.kind !== "image")}
                        title="Move up"
                        className="font-sans text-[11px] text-muted-ink hover:text-gold disabled:opacity-30 uppercase tracking-wide transition-colors px-1"
                      >
                        ↑
                      </button>
                      <button
                        data-testid={`composer-media-down-${idx}`}
                        onClick={() => moveMedia(idx, 1)}
                        disabled={idx === media.length - 1 || media.slice(idx + 1).every((x) => x.kind !== "image")}
                        title="Move down"
                        className="font-sans text-[11px] text-muted-ink hover:text-gold disabled:opacity-30 uppercase tracking-wide transition-colors px-1"
                      >
                        ↓
                      </button>
                    </>
                  )}
                  <button
                    data-testid={`composer-media-remove-${idx}`}
                    onClick={() => removeMedia(idx)}
                    className="font-sans text-[11px] text-muted-ink hover:text-deepred uppercase tracking-wide transition-colors px-2"
                  >
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Embed URL input */}
      {!video && !embed && (
        <div className="mt-3 flex items-center gap-2" data-testid="composer-embed-row">
          <input
            data-testid="composer-embed-url"
            placeholder="Paste a YouTube or Vimeo link"
            value={embedUrl}
            onChange={(e) => setEmbedUrl(e.target.value)}
            className="flex-1 bg-cream border hairline rounded-sm px-3 py-2 font-sans text-xs ink focus:outline-none focus:ring-1 focus:ring-gold"
          />
          <button
            data-testid="composer-embed-attach"
            onClick={attachEmbed}
            disabled={!embedUrl.trim()}
            className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 disabled:opacity-40 transition-opacity px-2"
          >
            Attach
          </button>
        </div>
      )}

      {isEssay && (
        <div className="mt-3 flex items-center gap-3 flex-wrap" data-testid="composer-schedule">
          <label className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink">Schedule</label>
          <input
            type="datetime-local"
            data-testid="composer-schedule-input"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            className="bg-cream border hairline rounded-sm px-2 py-1 font-sans text-xs ink focus:outline-none focus:ring-1 focus:ring-gold"
          />
          {scheduledAt && (
            <button onClick={() => setScheduledAt("")} data-testid="composer-schedule-clear" className="font-sans text-xs text-muted-ink hover:text-deepred transition-colors">
              Publish now instead
            </button>
          )}
        </div>
      )}

      {currentPrompt && (
        <div className="mt-3 border hairline rounded-sm p-3 bg-cream flex items-start gap-3" data-testid="composer-prompt-link">
          <input
            id="link-prompt"
            type="checkbox"
            checked={linkPrompt}
            onChange={(e) => setLinkPrompt(e.target.checked)}
            data-testid="composer-prompt-link-checkbox"
            className="mt-1 accent-gold cursor-pointer"
          />
          <label htmlFor="link-prompt" className="flex-1 cursor-pointer">
            <div className="font-sans text-[11px] uppercase tracking-wider font-semibold text-gold mb-0.5">This week's subject</div>
            <div className="font-display font-semibold text-sm ink leading-snug">{currentPrompt.title}</div>
          </label>
        </div>
      )}

      <div className="flex items-center justify-between mt-4 pt-3 border-t hairline gap-3 flex-wrap">
        <div className="flex items-center gap-4 flex-wrap">
          <label className={`cursor-pointer font-sans text-sm font-medium transition-colors ${uploading === "image 1" || images.length >= MAX_IMAGES ? "text-muted-ink/50 cursor-not-allowed" : "text-muted-ink hover:text-gold"}`}>
            {uploading.startsWith("image") ? "Uploading..." : images.length >= MAX_IMAGES ? `Images (${MAX_IMAGES}/${MAX_IMAGES})` : `Image${images.length ? ` (${images.length}/${MAX_IMAGES})` : ""}`}
            <input data-testid="composer-image-input" type="file" accept="image/*" multiple className="hidden"
              disabled={images.length >= MAX_IMAGES}
              onChange={(e) => { onImageInput(e.target.files); e.target.value = ""; }} />
          </label>
          <label className={`cursor-pointer font-sans text-sm font-medium transition-colors ${video || uploading === "video" ? "text-muted-ink/50 cursor-not-allowed" : "text-muted-ink hover:text-gold"}`}>
            {uploading === "video" ? "Uploading..." : video ? "Video attached" : "Video"}
            <input data-testid="composer-video-input" type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden"
              disabled={!!video || uploading === "video"}
              onChange={(e) => { onVideoInput(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
          <label className={`cursor-pointer font-sans text-sm font-medium transition-colors ${audio || uploading === "audio" ? "text-muted-ink/50 cursor-not-allowed" : "text-muted-ink hover:text-gold"}`}>
            {uploading === "audio" ? "Uploading..." : audio ? "Audio attached" : "Audio"}
            <input data-testid="composer-audio-input" type="file" accept="audio/*" className="hidden"
              disabled={!!audio || uploading === "audio"}
              onChange={(e) => { onAudioInput(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
          {savedLabel && <span data-testid="draft-saved" className="font-sans text-[11px] text-muted-ink italic">{savedLabel}</span>}
        </div>
        <div className="flex items-center gap-4">
          <span className="font-sans text-xs text-muted-ink">{text.length}/{isEssay ? "50000" : "500"}</span>
          <button
            data-testid="composer-publish"
            onClick={submit}
            disabled={posting || (!text.trim() && media.length === 0) || (isEssay && !title.trim()) || media.some((m) => m.processing)}
            className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {media.some((m) => m.processing)
              ? "Transcoding video..."
              : posting
              ? (isEssay ? (scheduledAt ? "Scheduling..." : "Publishing...") : "Queueing...")
              : (isEssay ? (scheduledAt ? "Schedule" : "Publish essay") : "Queue for release")}
          </button>
        </div>
      </div>
      <p className="mt-3 font-sans text-[11px] text-muted-ink">
        Images up to 6MB each (max {MAX_IMAGES}). Video up to 3 minutes (≤60s plays inline, longer videos auto-transcode). Audio up to 20MB and 5 minutes.
      </p>
    </section>
  );
}
