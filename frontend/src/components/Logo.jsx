import React from "react";
import { useBrand } from "@/brand/BrandContext.jsx";

export default function Logo({ size = 28, lockup = true }) {
  const { brand } = useBrand();
  const markSize = Math.max(24, size);

  return (
    <div className="flex items-center gap-3" aria-label={brand.name}>
      <div
        className="flex items-center justify-center rounded-lg font-semibold tracking-tight"
        style={{
          width: markSize,
          height: markSize,
          fontSize: markSize * 0.55,
          backgroundColor: "rgba(15, 163, 177, 0.12)",
          color: "#0FA3B1",
        }}
      >
        ++
      </div>
      {lockup && (
        <span className="font-semibold" style={{ fontSize: size * 0.6 }}>
          {brand.name}
        </span>
      )}
    </div>
  );
}
