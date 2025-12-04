// frontend/src/brand/BrandContext.jsx
import React, { createContext, useContext, useEffect, useMemo } from "react";
import { BRANDS } from "./brands";

const DEFAULT_KEY = "donecast";
const BrandCtx = createContext({ brand: BRANDS[DEFAULT_KEY], setBrandKey: () => {} });

export function BrandProvider({ children }) {
  const brand = useMemo(() => BRANDS[DEFAULT_KEY], []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const html = document.documentElement;
    html.classList.remove("brand-ppp", "brand-plusplus");
    html.classList.add(`brand-${brand.key}`);
    html.setAttribute("data-brand", brand.key);
    document.title = brand.name;
  }, [brand]);

  return (
    <BrandCtx.Provider value={{ brand, setBrandKey: () => {} }}>
      {children}
    </BrandCtx.Provider>
  );
}

export const useBrand = () => useContext(BrandCtx);
