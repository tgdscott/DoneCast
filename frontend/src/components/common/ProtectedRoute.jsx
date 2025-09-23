import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { makeApi } from "../../lib/apiClient.js";
import { useAuth } from "../../AuthContext.jsx";

export default function ProtectedRoute({ children }) {
  const { token } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | ok | unauthed

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();
    const api = makeApi(token);

    // Guard against indefinitely hanging requests by enforcing a timeout
    const timeoutMs = 10000; // 10s
    const t = setTimeout(() => controller.abort("timeout"), timeoutMs);

    api
      .get("/api/users/me", { signal: controller.signal })
      .then(() => { if (mounted) setStatus("ok"); })
      .catch(() => { if (mounted) setStatus("unauthed"); })
      .finally(() => clearTimeout(t));

    return () => {
      mounted = false;
      clearTimeout(t);
      controller.abort();
    };
  }, [token]);

  if (status === "loading") return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  // Use landing with login modal trigger (/?login=1) instead of a bare /login route.
  if (status === "unauthed") return <Navigate to="/?login=1" replace />;
  return children;
}
