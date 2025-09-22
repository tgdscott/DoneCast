import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { makeApi } from "../../lib/apiClient.js";
import { useAuth } from "../../AuthContext.jsx";

export default function ProtectedRoute({ children }) {
  const { token } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | ok | unauthed

  useEffect(() => {
    let mounted = true;
    const api = makeApi(token);
    api.get("/api/users/me")
      .then(() => { if (mounted) setStatus("ok"); })
      .catch(() => { if (mounted) setStatus("unauthed"); });
    return () => { mounted = false; };
  }, []);

  if (status === "loading") return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  // Use landing with login modal trigger (/?login=1) instead of a bare /login route.
  if (status === "unauthed") return <Navigate to="/?login=1" replace />;
  return children;
}
