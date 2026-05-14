import React from "react";

// Brand lotus mark (transparent PNG). Used as a small square icon on hero pages
// (About / PendingReview / Declined / Upgrade / UpgradeSuccess). The header
// uses the full wordmark directly (see Layout.jsx), not this component.
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
