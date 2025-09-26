from __future__ import annotations

from fastapi import FastAPI
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
media                  = _safe_import("api.routers.media")
gcs_uploads            = _safe_import("api.routers.gcs_uploads")
episodes               = _safe_import("api.routers.episodes")
spreaker               = _safe_import("api.routers.spreaker")
spreaker_oauth         = _safe_import("api.routers.spreaker_oauth")
templates              = _safe_import("api.routers.templates")
flubber                = _safe_import("api.routers.flubber")
users                  = _safe_import("api.routers.users")
admin                  = _safe_import("api.routers.admin")
podcasts               = _safe_import("api.routers.podcasts")
importer               = _safe_import("api.routers.importer")
public                 = _safe_import("api.routers.public")
waitlist_router        = _safe_import("api.routers.waitlist")
debug                  = _safe_import("api.routers.debug")
billing_router         = _safe_import("api.routers.billing")
billing_webhook_router = _safe_import("api.routers.billing_webhook")
notifications_router   = _safe_import("api.routers.notifications")
music_router           = _safe_import("api.routers.music")
ai_metadata            = _safe_import("api.routers.ai_metadata")
sections_router        = _safe_import("api.routers.sections")
ai_suggestions         = _safe_import("api.routers.ai_suggestions")
elevenlabs_router      = _safe_import("api.routers.elevenlabs")
media_tts_router       = _safe_import("api.routers.media_tts")
dashboard_router       = _safe_import("api.routers.dashboard")
recurring              = _safe_import("api.routers.recurring")
assemblyai_router      = _safe_import("api.routers.assemblyai_webhook")
media_upload_alias     = _safe_import("api.routers.media_upload_alias")

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
    _maybe(app, media)
    availability['media'] = media is not None
    _maybe(app, media_upload_alias)
    availability['media_upload_alias'] = media_upload_alias is not None
    _maybe(app, gcs_uploads)
    availability['gcs_uploads'] = gcs_uploads is not None

    # The rest (best-effort)
    _maybe(app, episodes)
    availability['episodes'] = episodes is not None
    _maybe(app, spreaker)
    availability['spreaker'] = spreaker is not None
    _maybe(app, spreaker_oauth)
    availability['spreaker_oauth'] = spreaker_oauth is not None
    _maybe(app, templates)
    availability['templates'] = templates is not None
    _maybe(app, flubber)
    availability['flubber'] = flubber is not None
    _maybe(app, users)
    availability['users'] = users is not None
    _maybe(app, admin)
    availability['admin'] = admin is not None
    _maybe(app, podcasts)
    availability['podcasts'] = podcasts is not None
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
    _maybe(app, billing_webhook_router)
    availability['billing_webhook_router'] = billing_webhook_router is not None
    _maybe(app, notifications_router)
    availability['notifications_router'] = notifications_router is not None
    _maybe(app, ai_metadata)
    availability['ai_metadata'] = ai_metadata is not None
    _maybe(app, sections_router)
    availability['sections_router'] = sections_router is not None
    _maybe(app, ai_suggestions)
    availability['ai_suggestions'] = ai_suggestions is not None
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

    # Cloud Tasks internal hook (no prefix: it already has /api/tasks)
    app.include_router(tasks_router)

    # Return availability map so callers can make fail-fast decisions at
    # startup (for example: fail in prod if critical routers are missing).
    return availability
