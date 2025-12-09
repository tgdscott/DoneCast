from __future__ import annotations

from fastapi import FastAPI, APIRouter, HTTPException
import logging
import traceback

# Always-present internal tasks router
from api.routers.tasks import router as tasks_router

log = logging.getLogger(__name__)


def _safe_import(mod: str, name: str = "router"):
    """Import router objects defensively; return None if missing/errors.

    This also logs the import exception including a stack trace so missing
    dependencies are visible in startup logs (helps avoid silent failures
    where the API is missing routes and the SPA is served instead).
    """
    # Try a few common variants to be tolerant of naming differences (e.g.
    # some older code used module names like `billing_router` while newer
    # files are `billing.py`). Log each failure to aid debugging.
    tried = []
    candidates = []
    # Only consider the provided module path as-is, plus a de-suffixed
    # variant when the caller uses a name like "billing_router".
    # Importing the same file under different module names (e.g., both
    # "api.routers.auth" and bare "auth") causes Python to execute the
    # module twice, which with SQLModel leads to duplicate table/class
    # registration and crashes under the reloader. Avoid that.
    if "." in mod:
        candidates.append(mod)
        if mod.endswith("_router"):
            candidates.append(mod[: -len("_router")])
    else:
        # Caller provided a short name (e.g., "billing"). Try the fully
        # qualified module first, then fall back to the bare name.
        fq = f"api.routers.{mod}"
        candidates.append(fq)
        candidates.append(mod)

    for candidate in candidates:
        try:
            m = __import__(candidate, fromlist=[name])
            val = getattr(m, name, None)
            if val is not None:
                return val
            # If module imported but didn't expose the expected attribute,
            # return the module itself (some code stores the module as var
            # and calls .router later) so treat that as success.
            return m
        except Exception as exc:
            # Record the repr and a short traceback for post-mortem analysis
            tb = traceback.format_exc()
            # Keep only the first few lines of traceback to avoid noisy logs
            tb_short = "\n".join(tb.splitlines()[:8])
            tried.append((candidate, repr(exc), tb_short))
            # Surface as a warning so startup logs show the failure details
            log.warning("_safe_import attempt failed for %s: %s", candidate, tb_short)

    # If all attempts failed, log a concise warning with the collected errors.
    log.warning("_safe_import failed for %s; attempts: %s", mod, tried)
    return None

# Optional routers (best-effort; skip if a module is absent in this branch)
health_router          = _safe_import("api.routers.health")
auth_me_router         = _safe_import("api.routers.auth_me")
auth                   = _safe_import("api.routers.auth")
if auth is None:
    # If the auth package failed to import (for example a failing optional
    # submodule like verification or terms), try to load the OAuth subrouter
    # directly so critical login endpoints (e.g. /api/auth/login/google) are
    # still available. This is defensive and logged so operators can see
    # which import path actually succeeded.
    try:
        m = __import__("api.routers.auth.oauth", fromlist=["router"])
        auth = m.router  # type: ignore[assignment]
        log.info("Imported auth.oauth subrouter as fallback to restore login endpoints")
    except Exception:
        log.warning("Fallback import of api.routers.auth.oauth failed; auth router unavailable")

# Also attempt to load the oauth subrouter directly. We will register this
# under `/api/auth` even if the aggregated auth package fails so Google login
# remains available. Any import failure is logged for diagnosis.
oauth_subrouter = None
try:
    oauth_subrouter = _safe_import("api.routers.auth.oauth")
    if oauth_subrouter is not None:
        log.info("Found oauth subrouter via _safe_import; will register under /api/auth")
    else:
        log.warning("OAuth subrouter not found; login endpoints will be unavailable unless auth package imports")
except Exception:
    oauth_subrouter = None
    log.exception("OAuth subrouter import failed; login endpoints will be unavailable")

# If the real oauth subrouter is unavailable, define a minimal fallback so
# /api/auth/login/google exists and returns a clear 503 instead of 404.
if oauth_subrouter is None:
    fallback_oauth_router = APIRouter()

    @fallback_oauth_router.get("/login/google")
    async def _oauth_login_unavailable():
        raise HTTPException(status_code=503, detail="Google login temporarily unavailable (oauth import failed)")

    @fallback_oauth_router.get("/google/callback")
    async def _oauth_callback_unavailable():
        raise HTTPException(status_code=503, detail="Google login temporarily unavailable (oauth import failed)")

    oauth_subrouter = fallback_oauth_router
    log.warning("Registered minimal OAuth fallback router: returns 503 instead of 404 while oauth import is broken")
media                  = _safe_import("api.routers.media")
gcs_uploads            = _safe_import("api.routers.gcs_uploads")
episodes               = _safe_import("api.routers.episodes")
templates              = _safe_import("api.routers.templates")
media_bundle_router    = _safe_import("api.routers.media_bundle")
flubber                = _safe_import("api.routers.flubber")
intern                 = _safe_import("api.routers.intern")
users                  = _safe_import("api.routers.users")
admin                  = _safe_import("api.routers.admin")  # Uses admin/__init__.py (modular structure)
if admin is None:
    log.error("CRITICAL: Admin router failed to import - admin endpoints will NOT work")
else:
    log.info("Admin router imported successfully: %s", type(admin))
podcasts               = _safe_import("api.routers.podcasts")
importer               = _safe_import("api.routers.importer")
public                 = _safe_import("api.routers.public")
waitlist_router        = _safe_import("api.routers.waitlist")
debug                  = _safe_import("api.routers.debug")
billing_router         = _safe_import("api.routers.billing")
billing_internal_router = _safe_import("api.routers.billing", "internal_router")
billing_config_router  = _safe_import("api.routers.billing_config")
billing_webhook_router = _safe_import("api.routers.billing_webhook")
billing_ledger_router  = _safe_import("api.routers.billing_ledger")
notifications_router   = _safe_import("api.routers.notifications")
music_router           = _safe_import("api.routers.music")
ai_metadata            = _safe_import("api.routers.ai_metadata")
sections_router        = _safe_import("api.routers.sections")
ai_suggestions         = _safe_import("api.routers.ai_suggestions")
transcripts_router     = _safe_import("api.routers.transcripts")
elevenlabs_router      = _safe_import("api.routers.elevenlabs")
media_tts_router       = _safe_import("api.routers.media_tts")
dashboard_router       = _safe_import("api.routers.dashboard")
recurring              = _safe_import("api.routers.recurring")
assemblyai_router      = _safe_import("api.routers.assemblyai_webhook")
media_upload_alias     = _safe_import("api.routers.media_upload_alias")
assistant_router       = _safe_import("api.routers.assistant")
rss_feed_router        = _safe_import("api.routers.rss_feed")
analytics_router       = _safe_import("api.routers.analytics")
contact_router         = _safe_import("api.routers.contact")
website_sections_router = _safe_import("api.routers.website_sections")
sites_router           = _safe_import("api.routers.sites")
website_publish_router = _safe_import("api.routers.podcasts.publish")
auphonic_router        = _safe_import("api.routers.episodes.auphonic")
# user_deletion_router is in admin/users.py (loaded via admin module)
speakers_router        = _safe_import("api.routers.speakers")
worker_health_router   = _safe_import("api.routers.worker_health")
affiliate_router       = _safe_import("api.routers.affiliate")
onboarding_router      = _safe_import("api.routers.onboarding")

def _maybe(app: FastAPI, r, prefix: str = "/api"):
    if r is not None:
        app.include_router(r, prefix=prefix)

def attach_routers(app: FastAPI) -> dict:
    # Minimal/core
    availability: dict = {}

    _maybe(app, health_router, prefix="")  # health router often exposes /api/health itself; keep "" to avoid double /api/api
    availability['health'] = health_router is not None
    _maybe(app, auth_me_router)
    availability['auth_me'] = auth_me_router is not None
    _maybe(app, auth)
    availability['auth'] = auth is not None
    # Always register the oauth subrouter independently so login routes stay
    # alive even when other auth submodules fail to import.
    if oauth_subrouter is not None:
        _maybe(app, oauth_subrouter, prefix="/api/auth")
        availability['auth_oauth_fallback'] = True
    else:
        availability['auth_oauth_fallback'] = False
    _maybe(app, media)
    availability['media'] = media is not None
    _maybe(app, media_bundle_router)
    availability['media_bundle_router'] = media_bundle_router is not None
    _maybe(app, media_upload_alias)
    availability['media_upload_alias'] = media_upload_alias is not None
    _maybe(app, gcs_uploads)
    availability['gcs_uploads'] = gcs_uploads is not None
    _maybe(app, assistant_router)
    availability['assistant'] = assistant_router is not None

    # The rest (best-effort)
    _maybe(app, episodes)
    availability['episodes'] = episodes is not None
    _maybe(app, templates)
    availability['templates'] = templates is not None
    _maybe(app, flubber)
    availability['flubber'] = flubber is not None
    _maybe(app, intern)
    availability['intern'] = intern is not None
    _maybe(app, users)
    availability['users'] = users is not None
    _maybe(app, admin)
    availability['admin'] = admin is not None
    _maybe(app, podcasts)
    availability['podcasts'] = podcasts is not None
    if podcasts is None:
        log.error("CRITICAL: Podcasts router failed to import - podcast endpoints will NOT work")
    else:
        log.info("Podcasts router registered successfully")
        # Log registered podcast routes for debugging
        podcast_routes = [r for r in app.routes if hasattr(r, 'path') and '/podcasts' in str(getattr(r, 'path', ''))]
        if podcast_routes:
            podcast_paths = [f"{getattr(r, 'methods', set())} {str(getattr(r, 'path', 'NO_PATH'))}" for r in podcast_routes[:10]]
            log.info("Sample registered podcast routes (%d total): %s", len(podcast_routes), podcast_paths)
        else:
            log.warning("WARNING: No podcast routes found in registered routes!")
    _maybe(app, importer)
    availability['importer'] = importer is not None
    _maybe(app, public)
    availability['public'] = public is not None
    _maybe(app, waitlist_router)
    availability['waitlist_router'] = waitlist_router is not None
    _maybe(app, debug)
    availability['debug'] = debug is not None
    _maybe(app, music_router)
    availability['music_router'] = music_router is not None
    _maybe(app, billing_router)
    availability['billing_router'] = billing_router is not None
    _maybe(app, billing_internal_router)
    availability['billing_internal_router'] = billing_internal_router is not None
    _maybe(app, billing_config_router)
    availability['billing_config_router'] = billing_config_router is not None
    _maybe(app, billing_webhook_router)
    availability['billing_webhook_router'] = billing_webhook_router is not None
    _maybe(app, billing_ledger_router)
    availability['billing_ledger_router'] = billing_ledger_router is not None
    _maybe(app, notifications_router)
    availability['notifications_router'] = notifications_router is not None
    _maybe(app, ai_metadata)
    availability['ai_metadata'] = ai_metadata is not None
    _maybe(app, sections_router)
    availability['sections_router'] = sections_router is not None
    _maybe(app, ai_suggestions)
    availability['ai_suggestions'] = ai_suggestions is not None
    _maybe(app, transcripts_router)
    availability['transcripts_router'] = transcripts_router is not None
    _maybe(app, elevenlabs_router)
    availability['elevenlabs_router'] = elevenlabs_router is not None
    _maybe(app, media_tts_router)
    availability['media_tts_router'] = media_tts_router is not None
    _maybe(app, dashboard_router)
    availability['dashboard_router'] = dashboard_router is not None
    _maybe(app, recurring)
    availability['recurring'] = recurring is not None
    _maybe(app, assemblyai_router)
    availability['assemblyai_router'] = assemblyai_router is not None
    _maybe(app, rss_feed_router, prefix="")  # RSS feeds at root level (/rss/...), not /api/rss
    availability['rss_feed_router'] = rss_feed_router is not None
    _maybe(app, analytics_router)
    availability['analytics_router'] = analytics_router is not None
    _maybe(app, contact_router)
    availability['contact_router'] = contact_router is not None
    _maybe(app, website_sections_router)
    availability['website_sections_router'] = website_sections_router is not None
    _maybe(app, sites_router)  # Public website serving
    availability['sites_router'] = sites_router is not None
    _maybe(app, website_publish_router)  # Website publishing & domain provisioning
    availability['website_publish_router'] = website_publish_router is not None
    _maybe(app, auphonic_router)  # Auphonic outputs for episode assembly
    availability['auphonic_router'] = auphonic_router is not None
    # user_deletion_router removed - deletion functionality is in admin/users.py
    _maybe(app, speakers_router)  # Speaker identification configuration
    availability['speakers_router'] = speakers_router is not None
    _maybe(app, worker_health_router)  # Local worker health check and fallback status
    availability['worker_health_router'] = worker_health_router is not None
    _maybe(app, affiliate_router, prefix="/api/affiliate")
    availability['affiliate_router'] = affiliate_router is not None
    _maybe(app, onboarding_router)
    availability['onboarding_router'] = onboarding_router is not None

    # Cloud Tasks internal hook (no prefix: it already has /api/tasks)
    app.include_router(tasks_router)

    # Log a concise availability summary so startup logs show which
    # namespaces were successfully registered. This helps debug cases
    # where an import-time error prevented a package from mounting routes.
    try:
        log.info("Router availability summary at startup: %s", availability)
    except Exception:
        log.warning("Failed to log router availability summary")

    # Temporary diagnostic endpoint: returns a list of registered routes
    # and the availability map. This is useful when operators report
    # missing endpoints (404) but startup logs are inconclusive.
    # Remove this endpoint after diagnosis.
    try:
        def _register_debug_routes(app: FastAPI):
            @app.get("/api/debug/routes")
            async def _debug_routes():
                routes = []
                for r in app.routes:
                    path = getattr(r, 'path', None) or getattr(r, 'path_regex', None) or str(r)
                    methods = list(getattr(r, 'methods', [])) if getattr(r, 'methods', None) else None
                    routes.append({"path": str(path), "methods": methods})
                return {"routes": routes, "availability": availability}

        _register_debug_routes(app)
        log.info("Temporary debug endpoint /api/debug/routes registered")
    except Exception:
        log.exception("Failed to register /api/debug/routes diagnostic endpoint")

    # Return availability map so callers can make fail-fast decisions at
    # startup (for example: fail in prod if critical routers are missing).
    return availability
