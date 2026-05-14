import React, { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { API } from "@/lib/api";

/**
 * Render media attached to a post: images (gallery), video (player with poster), audio, embed.
 * Backwards compat: if `media` is empty but `image_path` is set, render as a single image.
 */
export default function MediaBlock({ media, imagePath, compact = false }) {
  const items = (media && media.length ? media : (imagePath ? [{ kind: "image", path: imagePath }] : []));
  if (items.length === 0) return null;

  const images = items.filter((m) => m.kind === "image");
  const video = items.find((m) => m.kind === "video");
  const audio = items.find((m) => m.kind === "audio");
  const embed = items.find((m) => m.kind === "embed");

  return (
    <div className={`space-y-4 ${compact ? "" : "mt-5"}`} data-testid="media-block">
      {images.length > 0 && <Gallery images={images} compact={compact} />}
      {video && <VideoPlayer video={video} />}
      {embed && <EmbedPlayer embed={embed} />}
      {audio && <AudioPlayer audio={audio} />}
    </div>
  );
}

function Gallery({ images, compact }) {
  const n = images.length;
  const cls =
    n === 1 ? "grid grid-cols-1"
    : n === 2 ? "grid grid-cols-2 gap-1"
    : n === 3 ? "grid grid-cols-2 gap-1"
    : "grid grid-cols-2 gap-1";
  const maxH = compact ? "max-h-[280px]" : "max-h-[520px]";
  return (
    <div className={`${cls} border hairline rounded-sm overflow-hidden`} data-testid="media-gallery">
      {images.map((img, idx) => {
        // For 3 images: first is wide, next two stacked
        const isFirstOfThree = n === 3 && idx === 0;
        const url = `${API}/uploads/file/${img.path}`;
        return (
          <a
            key={img.path || idx}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`media-image-${idx}`}
            className={`block overflow-hidden bg-[#F5EDD6] ${isFirstOfThree ? "row-span-2" : ""}`}
          >
            <img
              src={url}
              alt=""
              className={`w-full h-full object-cover ${n === 1 ? maxH : "aspect-square"}`}
            />
          </a>
        );
      })}
    </div>
  );
}

function VideoPlayer({ video }) {
  const src = video.path ? `${API}/uploads/file/${video.path}` : null;
  const hlsSrc = video.hls_path ? `${API}/uploads/file/${video.hls_path}` : null;
  const poster = video.thumbnail_path ? `${API}/uploads/file/${video.thumbnail_path}` : undefined;
  const videoRef = useRef(null);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !hlsSrc) return;
    // Safari can play HLS natively
    if (el.canPlayType("application/vnd.apple.mpegurl")) {
      el.src = hlsSrc;
      return;
    }
    if (Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true });
      hls.loadSource(hlsSrc);
      hls.attachMedia(el);
      return () => { try { hls.destroy(); } catch (e) { /* ignore */ } };
    }
    // Fallback: try setting src directly
    el.src = hlsSrc;
  }, [hlsSrc]);

  return (
    <div className="border hairline rounded-sm overflow-hidden bg-black" data-testid="media-video">
      <video
        ref={videoRef}
        controls
        playsInline
        preload="metadata"
        poster={poster}
        className="w-full max-h-[520px]"
      >
        {!hlsSrc && src && <source src={src} type={video.mime || "video/mp4"} />}
      </video>
    </div>
  );
}

function EmbedPlayer({ embed }) {
  if (!embed.embed_url) return null;
  return (
    <div className="border hairline rounded-sm overflow-hidden bg-black aspect-video" data-testid="media-embed">
      <iframe
        src={embed.embed_url}
        title={`${embed.provider} video`}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className="w-full h-full border-0"
      />
    </div>
  );
}

function AudioPlayer({ audio }) {
  const src = `${API}/uploads/file/${audio.path}`;
  const audioRef = useRef(null);
  const [duration, setDuration] = useState(audio.duration_s || 0);
  const [progress, setProgress] = useState(0); // 0..1
  const [playing, setPlaying] = useState(false);
  const peaks = Array.isArray(audio.peaks) && audio.peaks.length ? audio.peaks : null;

  const fmt = (s) => {
    if (!Number.isFinite(s) || s <= 0) return "0:00";
    const m = Math.floor(s / 60);
    const ss = Math.floor(s % 60).toString().padStart(2, "0");
    return `${m}:${ss}`;
  };

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) { el.play(); setPlaying(true); }
    else { el.pause(); setPlaying(false); }
  };

  const onTime = () => {
    const el = audioRef.current;
    if (!el || !el.duration) return;
    setProgress(el.currentTime / el.duration);
  };

  const seekTo = (e) => {
    const el = audioRef.current;
    if (!el || !el.duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    el.currentTime = ratio * el.duration;
    setProgress(ratio);
  };

  return (
    <div className="border hairline rounded-sm bg-cream p-4" data-testid="media-audio">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={toggle}
          data-testid="audio-play-toggle"
          aria-label={playing ? "Pause" : "Play"}
          className="w-10 h-10 rounded-full bg-gold text-cream flex items-center justify-center hover:opacity-90 transition-opacity shrink-0"
        >
          {playing ? (
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor"><path d="M7 5v14l12-7z" /></svg>
          )}
        </button>
        {peaks ? (
          <button
            type="button"
            onClick={seekTo}
            aria-label="Seek"
            data-testid="audio-waveform"
            className="flex-1 h-12 flex items-center gap-[2px] cursor-pointer min-w-0"
          >
            {peaks.map((p, i) => {
              const ratio = i / peaks.length;
              const past = ratio <= progress;
              const h = Math.max(2, Math.round(p * 40));
              return (
                <span
                  key={i}
                  style={{ height: `${h}px`, width: `calc((100% - ${(peaks.length - 1) * 2}px) / ${peaks.length})` }}
                  className={`rounded-[1px] ${past ? "bg-gold" : "bg-[#E8D4A0]"}`}
                />
              );
            })}
          </button>
        ) : (
          <div className="flex-1 font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">
            Audio
          </div>
        )}
        <span className="font-sans text-xs text-muted-ink tabular-nums shrink-0">{fmt(duration)}</span>
      </div>
      <audio
        ref={audioRef}
        preload="metadata"
        onLoadedMetadata={(e) => !duration && setDuration(e.currentTarget.duration || 0)}
        onTimeUpdate={onTime}
        onEnded={() => { setPlaying(false); setProgress(0); }}
        className="hidden"
      >
        <source src={src} type={audio.mime || "audio/mpeg"} />
      </audio>
    </div>
  );
}
