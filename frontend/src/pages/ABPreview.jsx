import React from "react";
import AppAB from "../ab/AppAB";
import { useAuth } from "@/AuthContext";

export default function ABPreview() {
  const { token, isAuthenticated } = useAuth() || {};
  if (!isAuthenticated) {
    // Hard gate: unauth users cannot access the experimental workspace
    try { window.location.replace('/'); } catch(_) {}
    return null;
  }
  return <AppAB token={token} />;
}
