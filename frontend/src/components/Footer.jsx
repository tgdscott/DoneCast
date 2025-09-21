import React from "react";
import { useBrand } from "@/brand/BrandContext.jsx";

export default function Footer() {
  const { brand } = useBrand();
  return (
    <footer className="border-t mt-12 py-8 text-sm text-muted-foreground">
      <div className="container mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>© {new Date().getFullYear()} {brand.key === "nsc" ? "No Sweat" : "Podcast Plus"}</div>
        <nav className="flex items-center gap-4">
          <a href="/privacy" className="hover:text-foreground">Privacy Policy</a>
          <a href="/terms" className="hover:text-foreground">Terms of Use</a>
        </nav>
        <div>
          {brand.key === "nsc" ? (
            <span className="inline-flex items-center gap-2">
              <span>Made with No Sweat</span>
              <img src="/nsc_mark_lite.svg" width="16" height="16" alt="" />
            </span>
          ) : (
            <span>Podcast Plus</span>
          )}
        </div>
      </div>
    </footer>
  );
}
