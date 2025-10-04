# Investigation: 404 from `/api/intern/prepare-by-file`

## Summary
A `POST` to `/api/intern/prepare-by-file` returning HTTP 404 means the FastAPI router that exposes the intern endpoints never mounted. The `sentry disabled` console message is unrelated; it simply indicates no Sentry DSN is configured for the frontend bundle.

## Likely causes and fixes

1. **Missing backend dependency prevents `api.routers.intern` from importing.**
   * The API loads routers with a defensive `_safe_import` helper; if an import raises (for example because a dependency is missing), the router is skipped and every endpoint under it returns 404 because it was never registered.【F:backend/api/routing.py†L13-L132】
   * The intern router depends on `api.routers.auth.get_current_user`. When the `auth` package fails to import (e.g., because the `python-jose` or `passlib` packages are absent), `_safe_import` logs the failure and the intern router fails too.【F:backend/api/routers/intern.py†L18-L241】【F:logs.txt†L70-L92】
   * **Fix:** Check the API startup logs for `_safe_import` warnings referencing `api.routers.intern` or its dependencies. Install the missing packages in the deployment (most commonly `python-jose`, `passlib`, `authlib`, or other auth stack requirements) and redeploy so the router mounts.

2. **Backend deployment is running an older build that predates the intern endpoints.**
   * If the Cloud Run (or other) service has not been redeployed with the commit that introduced `prepare-by-file`, the router will legitimately be missing even if dependencies are present. In that case the SPA will call an endpoint the backend does not know about, yielding 404.
   * **Fix:** Verify the running service revision/commit. Redeploy the backend with the revision that contains `backend/api/routers/intern.py` and confirm the health endpoint advertises the intern routes in its availability map.【F:backend/api/routing.py†L120-L143】

3. **Traffic is routed to a minimal or fallback environment that omits optional routers.**
   * The routing helper treats most routers as optional, so staging or fallback environments that intentionally omit heavy dependencies (e.g., audio processing libraries such as `pydub` and ffmpeg) will silently skip mounting the intern routes, also causing 404s.【F:backend/api/routing.py†L13-L143】
   * **Fix:** Ensure the environment handling the request is the full production stack, or, if this is intentional (e.g., a lightweight worker), update the frontend configuration so intern actions target an environment that includes the full audio toolchain.

## Next steps
1. Inspect the API startup logs in the affected environment for `_safe_import` warnings and resolve any missing dependency errors first.
2. Confirm the running service revision matches the commit that introduced the intern endpoints.
3. After fixes, send a smoke request to `/api/intern/prepare-by-file` and ensure it returns 200/400 (validation error) rather than 404.
