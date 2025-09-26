import React from "react";
import { useBrand } from "@/brand/BrandContext.jsx";

export default function Footer() {
  const { brand } = useBrand();
  return (
    <footer className="border-t mt-12 py-8 text-sm text-muted-foreground">
      <div className="container mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>© {new Date().getFullYear()} {brand.name}</div>
        <nav className="flex items-center gap-4">
          <a href="/privacy" className="hover:text-foreground">Privacy Policy</a>
          <a href="/terms" className="hover:text-foreground">Terms of Use</a>
        </nav>
        <div className="inline-flex items-center gap-2 text-primary">
          <span className="font-medium">Made with {brand.shortName}</span>
          <span aria-hidden="true" className="text-lg leading-none">++</span>
        </div>
      </div>
    </footer>
  );
}
