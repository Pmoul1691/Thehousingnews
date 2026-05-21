import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import api, { API } from "@/lib/api";
import { toast } from "sonner";
import FloatingToolbar from "@/components/FloatingToolbar";
import PublishDrawer from "@/components/PublishDrawer";

// TipTap + ProseMirror weigh ~120 kB gzipped. They're only needed when an
// author opens the visual essay editor, so we ship them as a separate chunk
// that the browser fetches the first time RichTextEditor mounts. The
// markdown editor (just a <textarea>) stays in this main composer chunk.
const RichTextEditor = lazy(() => import("@/components/RichTextEditor"));

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
  const [regions, setRegions] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [postingStartedAt, setPostingStartedAt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const textareaRef = useRef(null);
  const draftDirty = useRef(false);

  // Live "Publishing… 3s" counter so the user knows the request is still in flight
  // (and the spinner isn't dead). Resets when posting flips back to false.
  useEffect(() => {
    if (!posting) { setElapsed(0); return undefined; }
    const t = setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - postingStartedAt) / 1000)));
    }, 250);
    return () => clearInterval(t);
  }, [posting, postingStartedAt]);

  const images = useMemo(() => media.filter((m) => m.kind === "image"), [media]);
  const video = useMemo(() => media.find((m) => m.kind === "video"), [media]);
  const audio = useMemo(() => media.find((m) => m.kind === "audio"), [media]);
  const embed = useMemo(() => media.find((m) => m.kind === "embed"), [media]);

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
    setPostingStartedAt(Date.now());
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
        regions: regions.length > 0 ? regions : undefined,
      });
      if (mode === "essay") {
        if (r.data.status === "scheduled") toast.success("Essay scheduled");
        else toast.success("Essay published. Emails are going out now.");
      } else {
        toast.success(`Queued for ${formatLocal(r.data.release_at)} CT`);
      }
      // Close the drawer + flip spinner off immediately. Cleanup (clearing the
      // draft + refetching writer stats) happens in the background so a slow
      // /drafts or /me/writer/* call never leaves the spinner stuck.
      setDrawerOpen(false);
      setPosting(false);
      reset().catch(() => {});
      if (onPosted) {
        try { Promise.resolve(onPosted()).catch(() => {}); } catch (_e) {}
      }
    } catch (e) {
      const msg = e?.code === "ECONNABORTED"
        ? "Publish timed out. Check your connection and try again."
        : (e?.response?.data?.detail || "Could not publish");
      toast.error(msg);
      setPosting(false);
    }
  };

  const releaseLabel = nextWindow ? formatLocal(nextWindow.next_release_iso) : "";
  const isEssay = mode === "essay";
  const savedLabel = savedAt ? `Draft saved at ${savedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "";

  const mediaSummary = useMemo(() => ({
    images: images.length,
    video: video ? (video.processing ? "transcoding..." : (video.duration_s ? `${Math.round(video.duration_s)}s` : "attached")) : "",
    audio: audio ? (audio.duration_s ? `${Math.round(audio.duration_s)}s` : "attached") : "",
    embed: embed ? `${embed.provider} ${embed.video_id}` : "",
  }), [images.length, video, audio, embed]);

  const canPublish = (text.trim() || media.length > 0) && (!isEssay || title.trim()) && !media.some((m) => m.processing);
  const publishLabel = posting
    ? (isEssay ? (scheduledAt ? "Scheduling…" : "Publishing…") : "Queueing…")
    : (isEssay ? (scheduledAt ? "Schedule essay" : "Publish essay now") : `Queue for ${releaseLabel || "next drop"} CT`);

  return (
    <section data-testid="inline-composer-container" className="border hairline rounded-sm p-6 sm:p-10 bg-cream relative">
      {/* Mode toggle + release indicator */}
      <div className="flex items-center justify-between mb-8 gap-3 flex-wrap">
        <div
          className="inline-flex bg-white/60 border border-gold/20 rounded-full p-1"
          data-testid="composer-mode-toggle"
        >
          <button
            data-testid="composer-mode-post"
            onClick={() => setMode("post")}
            className={`px-5 py-1.5 rounded-full font-sans text-xs font-semibold uppercase tracking-wider transition-all ${mode === "post" ? "bg-[#1D2D44] text-cream shadow-sm" : "text-muted-ink hover:text-ink"}`}
          >
            Short post
          </button>
          <button
            data-testid="composer-mode-essay"
            onClick={() => setMode("essay")}
            className={`px-5 py-1.5 rounded-full font-sans text-xs font-semibold uppercase tracking-wider transition-all ${mode === "essay" ? "bg-[#1D2D44] text-cream shadow-sm" : "text-muted-ink hover:text-ink"}`}
          >
            Essay
          </button>
        </div>
        <p className="font-sans text-xs text-muted-ink" data-testid="composer-release-note">
          {isEssay ? (
            scheduledAt ? (<>Publishes <span className="font-semibold ink">{new Date(scheduledAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span></>)
              : (<>Publishes <span className="font-semibold ink">now</span> when you confirm</>)
          ) : (
            releaseLabel ? (<>Releases at <span className="font-semibold ink">{releaseLabel} CT</span></>) : null
          )}
        </p>
      </div>

      {/* Title-first essay header */}
      {isEssay && (
        <div className="mb-8 space-y-3">
          <textarea
            data-testid="editor-title-input"
            placeholder="Title"
            value={title}
            maxLength={160}
            rows={1}
            onInput={(e) => {
              e.target.style.height = "auto";
              e.target.style.height = `${e.target.scrollHeight}px`;
            }}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-transparent border-0 focus:outline-none focus:ring-0 resize-none overflow-hidden font-display font-semibold text-4xl sm:text-5xl ink tracking-tight leading-[1.1] placeholder:text-ink/25 placeholder:font-display p-0"
          />
          <input
            data-testid="composer-subtitle"
            placeholder="A subtitle to set the stakes (optional)"
            value={subtitle}
            maxLength={240}
            onChange={(e) => setSubtitle(e.target.value)}
            className="w-full bg-transparent border-0 focus:outline-none focus:ring-0 font-serif italic text-xl text-muted-ink placeholder:text-ink/25 p-0"
          />
        </div>
      )}

      {/* Essay visual/markdown sub-toggle */}
      {isEssay && (
        <div className="flex items-center gap-1 mb-3 border hairline rounded-sm p-0.5 w-fit" data-testid="essay-editor-toggle">
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

      {/* Writing surface */}
      {isEssay && editorMode === "visual" ? (
        <Suspense
          fallback={
            <div
              data-testid="rte-loading"
              className="min-h-[400px] flex items-center justify-center text-muted-ink text-sm"
              aria-busy="true"
              aria-live="polite"
            >
              <div className="w-5 h-5 rounded-full border-2 border-slate-200 border-t-slate-500 animate-spin mr-2" />
              Loading editor…
            </div>
          }
        >
          <RichTextEditor
            value={text}
            onChange={setText}
            placeholder="Write the essay. Type / to insert headings, images, video, audio, or links."
          />
        </Suspense>
      ) : (
        <>
          <textarea
            ref={textareaRef}
            data-testid="editor-body-textarea"
            className={`w-full bg-transparent border-0 focus:outline-none focus:ring-0 font-serif ink leading-relaxed resize-none ${isEssay ? "min-h-[400px] text-lg sm:text-xl" : "min-h-[150px] text-base sm:text-lg"}`}
            placeholder={isEssay ? "Begin writing. Markdown is supported: **bold**, _italic_, # heading, - lists, > quotes, [link](url)." : "Plain words. What happened on a deal today?"}
            value={text}
            maxLength={isEssay ? 50000 : 500}
            onChange={(e) => setText(e.target.value)}
          />
          <FloatingToolbar editorRef={textareaRef} onChange={setText} active />
        </>
      )}
      <p className="mt-2 font-sans text-[11px] text-muted-ink/80" data-testid="composer-tag-hint">
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
              <div key={idx} data-testid={`composer-media-${idx}`} className="flex items-center justify-between gap-3 px-3 py-2 border hairline rounded-sm bg-white/60">
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
        <div className="mt-4 flex items-center gap-2" data-testid="composer-embed-row">
          <input
            data-testid="composer-embed-url"
            placeholder="Paste a YouTube or Vimeo link"
            value={embedUrl}
            onChange={(e) => setEmbedUrl(e.target.value)}
            className="flex-1 bg-white/60 border hairline rounded-sm px-3 py-2 font-sans text-xs ink focus:outline-none focus:ring-1 focus:ring-gold"
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

      {/* Editor action bar — attach + Next */}
      <div className="flex items-center justify-between mt-6 pt-4 border-t hairline gap-3 flex-wrap">
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
            data-testid="open-publish-drawer-button"
            onClick={() => setDrawerOpen(true)}
            disabled={!canPublish}
            className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-full hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {isEssay ? "Publish settings →" : "Queue for release →"}
          </button>
        </div>
      </div>
      <p className="mt-3 font-sans text-[11px] text-muted-ink">
        Images up to 6MB each (max {MAX_IMAGES}). Video up to 3 minutes (≤60s plays inline, longer videos auto-transcode). Audio up to 20MB and 5 minutes.
      </p>

      {/* Publish settings drawer */}
      <PublishDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        mode={mode}
        scheduledAt={scheduledAt}
        setScheduledAt={setScheduledAt}
        releaseLabel={releaseLabel}
        mediaSummary={mediaSummary}
        regions={regions}
        setRegions={setRegions}
        currentPrompt={currentPrompt}
        linkPrompt={linkPrompt}
        setLinkPrompt={setLinkPrompt}
        onPublish={submit}
        posting={posting}
        postingElapsed={elapsed}
        canPublish={canPublish}
        publishLabel={publishLabel}
      />
    </section>
  );
}
