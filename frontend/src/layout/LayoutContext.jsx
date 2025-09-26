import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from "react";

const LAYOUT_STORAGE_KEY = "ppp_layout_choice";
const LAYOUT_MODE_KEY = "ppp_layout_mode";

const LAYOUTS = {
  regular: { key: "regular", label: "Regular workspace" },
  ab: { key: "ab", label: "Plus Plus workspace" }
};

const DEFAULT_STATE = { key: "regular", mode: "manual" };

function ensureAssignment() {
  try {
    const saved = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (saved === "regular" || saved === "ab") return saved;
    const assigned = Math.random() < 0.5 ? "regular" : "ab";
    localStorage.setItem(LAYOUT_STORAGE_KEY, assigned);
    return assigned;
  } catch {
    return "regular";
  }
}

function readInitialState() {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const params = new URLSearchParams(window.location.search);
    const qp = params.get("layout");
    if (qp === "regular" || qp === "ab") {
      localStorage.setItem(LAYOUT_STORAGE_KEY, qp);
      localStorage.setItem(LAYOUT_MODE_KEY, "manual");
      return { key: qp, mode: "manual" };
    }
    if (qp === "auto") {
      const assigned = ensureAssignment();
      localStorage.setItem(LAYOUT_MODE_KEY, "auto");
      return { key: assigned, mode: "auto" };
    }

    const storedMode = localStorage.getItem(LAYOUT_MODE_KEY);
    const storedKey = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (storedMode === "manual") {
      if (storedKey === "regular" || storedKey === "ab") {
        return { key: storedKey, mode: "manual" };
      }
      localStorage.setItem(LAYOUT_STORAGE_KEY, DEFAULT_STATE.key);
      localStorage.setItem(LAYOUT_MODE_KEY, "manual");
      return DEFAULT_STATE;
    }
    if (storedMode === "auto") {
      const assigned = ensureAssignment();
      return { key: assigned, mode: "auto" };
    }
    if (storedKey === "regular" || storedKey === "ab") {
      localStorage.setItem(LAYOUT_MODE_KEY, "manual");
      return { key: storedKey, mode: "manual" };
    }
    localStorage.setItem(LAYOUT_STORAGE_KEY, DEFAULT_STATE.key);
    localStorage.setItem(LAYOUT_MODE_KEY, DEFAULT_STATE.mode);
    return DEFAULT_STATE;
  } catch {
    return DEFAULT_STATE;
  }
}

const LayoutCtx = createContext({
  layout: LAYOUTS.regular,
  layoutKey: "regular",
  layoutMode: "manual",
  setLayout: () => {}
});

export function LayoutProvider({ children }) {
  const [state, setState] = useState(() => readInitialState());

  useEffect(() => {
    if (typeof document === "undefined") return;
    const html = document.documentElement;
    html.setAttribute("data-layout", state.key);
    html.setAttribute("data-layout-mode", state.mode);
  }, [state]);

  const layout = useMemo(() => LAYOUTS[state.key] || LAYOUTS.regular, [state.key]);

  const setLayout = useCallback((nextKey, nextMode = "manual") => {
    setState({ key: nextKey, mode: nextMode });
    try {
      localStorage.setItem(LAYOUT_STORAGE_KEY, nextKey);
      localStorage.setItem(LAYOUT_MODE_KEY, nextMode);
    } catch {}
  }, []);

  const value = useMemo(
    () => ({ layout, layoutKey: state.key, layoutMode: state.mode, setLayout }),
    [layout, state.key, state.mode, setLayout]
  );

  return <LayoutCtx.Provider value={value}>{children}</LayoutCtx.Provider>;
}

export function useLayout() {
  return useContext(LayoutCtx);
}

export { LAYOUTS, LAYOUT_STORAGE_KEY, LAYOUT_MODE_KEY };
