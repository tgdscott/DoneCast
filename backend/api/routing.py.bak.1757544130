from __future__ import annotations

from fastapi import FastAPI

# Always-present internal tasks router
from api.routers.tasks import router as tasks_router

def _safe_import(mod: str, name: str = "router"):
    """Import router objects defensively; return None if missing/errors."""
    try:
        m = __import__(mod, fromlist=[name])
        return getattr(m, name, None)
    except Exception:
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
waitlist_router        = _safe_import("api.routers.waitlist_router")
debug                  = _safe_import("api.routers.debug")
music_router           = _safe_import("api.routers.music_router")
billing_router         = _safe_import("api.routers.billing_router")
billing_webhook_router = _safe_import("api.routers.billing_webhook_router")
notifications_router   = _safe_import("api.routers.notifications_router")
ai_metadata            = _safe_import("api.routers.ai_metadata")
sections_router        = _safe_import("api.routers.sections_router")
ai_suggestions         = _safe_import("api.routers.ai_suggestions")
elevenlabs_router      = _safe_import("api.routers.elevenlabs_router")
media_tts_router       = _safe_import("api.routers.media_tts_router")
dashboard_router       = _safe_import("api.routers.dashboard_router")
recurring              = _safe_import("api.routers.recurring")

def _maybe(app: FastAPI, r, prefix: str = "/api"):
    if r is not None:
        app.include_router(r, prefix=prefix)

def attach_routers(app: FastAPI) -> None:
    # Minimal/core
    _maybe(app, health_router, prefix="")  # health router often exposes /api/health itself; keep "" to avoid double /api/api
    _maybe(app, auth_me_router)
    _maybe(app, auth)
    _maybe(app, media)
    _maybe(app, gcs_uploads)

    # The rest (best-effort)
    _maybe(app, episodes)
    _maybe(app, spreaker)
    _maybe(app, spreaker_oauth)
    _maybe(app, templates)
    _maybe(app, flubber)
    _maybe(app, users)
    _maybe(app, admin)
    _maybe(app, podcasts)
    _maybe(app, importer)
    _maybe(app, public)
    _maybe(app, waitlist_router)
    _maybe(app, debug)
    _maybe(app, music_router)
    _maybe(app, billing_router)
    _maybe(app, billing_webhook_router)
    _maybe(app, notifications_router)
    _maybe(app, ai_metadata)
    _maybe(app, sections_router)
    _maybe(app, ai_suggestions)
    _maybe(app, elevenlabs_router)
    _maybe(app, media_tts_router)
    _maybe(app, dashboard_router)
    _maybe(app, recurring)

    # Cloud Tasks internal hook (no prefix: it already has /api/tasks)
    app.include_router(tasks_router)
