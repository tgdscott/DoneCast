import React from "react";
import { useBrand } from "@/brand/BrandContext.jsx";

export default function Logo({ size = 28, lockup = true, src }) {
  const { brand } = useBrand();
  const markSize = Math.max(24, size);
  const [imgFailed, setImgFailed] = React.useState(false);
  // Prefer SVG if present, then PNG. Served from Vite's public/ folder at runtime.
  const imgSrc = src || "/logo.png";
  const pngFallback = "/logo.png";

  return (
    <div className="flex items-center gap-3" aria-label={brand.name}>
      {!imgFailed ? (
        <picture>
          {/* Try SVG first; if it 404s, the img will attempt PNG; onError -> fallback mark */}
          <source srcSet={imgSrc} type="image/png" />
          <img
            className="logo"
            src={pngFallback}
            alt={brand.name}
            width={markSize}
            height={markSize}
            style={{ width: markSize, height: markSize, objectFit: "contain" }}
            onError={() => setImgFailed(true)}
          />
        </picture>
      ) : (
        <div
          className="flex items-center justify-center rounded-lg font-semibold tracking-tight logo"
          style={{
            width: markSize,
            height: markSize,
            fontSize: markSize * 0.55,
            backgroundColor: "rgba(15, 163, 177, 0.12)",
            color: "#0FA3B1",
          }}
          aria-hidden="true"
        >
          DC
        </div>
      )}
      {lockup && (
        <span className="font-semibold" style={{ fontSize: size * 0.6 }}>
          {brand.name}
        </span>
      )}
    </div>
  );
}
