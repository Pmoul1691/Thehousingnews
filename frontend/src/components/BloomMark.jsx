import React from "react";

const SVG_URL = "https://customer-assets.emergentagent.com/job_0876d56f-54de-4e6e-9735-44bafdfed776/artifacts/21f0cb41_Gold.svg";

export default function BloomMark({ size = 28, className = "", alt = "The Ultradian Network" }) {
  return (
    <img
      src={SVG_URL}
      alt={alt}
      width={size}
      height={size}
      style={{ width: size, height: size }}
      className={className}
      draggable={false}
    />
  );
}
