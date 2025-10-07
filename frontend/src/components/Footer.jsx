import React from "react";
import { useBrand } from "@/brand/BrandContext.jsx";

export default function Footer() {
  const { brand } = useBrand();
  return (
    <footer className="border-t mt-12 py-8 text-sm text-muted-foreground">
      <div className="container mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div>© {new Date().getFullYear()} {brand.name}</div>
          <div className="text-xs">Patent Pending (App. No. 63/894,250)</div>
        </div>
        <nav className="flex items-center gap-4">
          <a href="/privacy" className="hover:text-foreground">Privacy Policy</a>
          <a href="/terms" className="hover:text-foreground">Terms of Use</a>
          <a href="/legal" className="hover:text-foreground">Legal</a>
        </nav>
        <div className="inline-flex items-center gap-2 text-primary">
          <span className="font-medium">Made with {brand.shortName}</span>
          <span aria-hidden="true" className="text-lg leading-none">++</span>
        </div>
      </div>
    </footer>
  );
}
