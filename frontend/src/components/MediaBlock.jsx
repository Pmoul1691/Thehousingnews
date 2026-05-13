import React, { useState } from "react";
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
  const src = `${API}/uploads/file/${video.path}`;
  const poster = video.thumbnail_path ? `${API}/uploads/file/${video.thumbnail_path}` : undefined;
  return (
    <div className="border hairline rounded-sm overflow-hidden bg-black" data-testid="media-video">
      <video
        controls
        playsInline
        preload="metadata"
        poster={poster}
        className="w-full max-h-[520px]"
      >
        <source src={src} type={video.mime || "video/mp4"} />
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
  const [duration, setDuration] = useState(audio.duration_s || 0);
  return (
    <div className="border hairline rounded-sm bg-cream p-4 flex items-center gap-3" data-testid="media-audio">
      <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold shrink-0">
        Audio{duration ? ` . ${Math.round(duration)}s` : ""}
      </div>
      <audio
        controls
        preload="metadata"
        onLoadedMetadata={(e) => !duration && setDuration(e.currentTarget.duration || 0)}
        className="flex-1 min-w-0"
      >
        <source src={src} type={audio.mime || "audio/mpeg"} />
      </audio>
    </div>
  );
}
