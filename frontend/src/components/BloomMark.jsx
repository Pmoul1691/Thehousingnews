import React from "react";

// Lotus mark from the brand image. Used as a small square icon (e.g. footer,
// landing hero, about hero, PendingReview). The header uses the full wordmark
// directly (see Layout.jsx), not BloomMark.
const MARK_URL = "/brand/logo-mark.png";

export default function BloomMark({ size = 28, className = "", alt = "The Housing News" }) {
  return (
    <img
      src={MARK_URL}
      alt={alt}
      width={size}
      height={size}
      style={{ width: size, height: size, objectFit: "contain" }}
      className={className}
      draggable={false}
    />
  );
}
