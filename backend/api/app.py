from __future__ import annotations
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware  # type: ignore
except Exception:  # pragma: no cover - older starlette
    ProxyHeadersMiddleware = None  # type: ignore
from starlette.requests import Request as StarletteRequest
from starlette.staticfiles import StaticFiles

# Load settings early
from api.core.config import settings
# Import paths *after* settings are loaded, as paths might use env vars
from api.core.paths import FINAL_DIR, MEDIA_DIR, FLUBBER_CTX_DIR

# Now, other modules can be imported that might use settings
import api.db_listeners  # registers SQLAlchemy listeners
from api.core.database import engine
from api.core.logging import configure_logging, get_logger
from api.exceptions import install_exception_handlers
from api.limits import limiter, DISABLE as RL_DISABLED
from api.startup_tasks import run_startup_tasks, _compute_pt_expiry
from api.routing import attach_routers

# --- logging ASAP ---
configure_logging()
log = get_logger("api.app")

# Suppress noisy passlib bcrypt version warning in dev (harmless but distracting)
try:  # pragma: no cover - defensive logging tweak
    import logging as _logging
    _pl_logger = _logging.getLogger("passlib.handlers.bcrypt")
    # Downgrade to ERROR so the trapped version attribute warning is hidden
    _pl_logger.setLevel(_logging.ERROR)
    # Patch missing __about__.__version__ to satisfy passlib check (older wheels)
    import bcrypt as _bcrypt  # type: ignore
    if _bcrypt and not getattr(_bcrypt, "__about__", None):
        class _About:  # minimal shim
            __version__ = getattr(_bcrypt, "__version__", "unknown")
        _bcrypt.__about__ = _About()  # type: ignore[attr-defined]
except Exception:
    pass

# --- Sentry (optional) ---
SENTRY_DSN = os.getenv("SENTRY_DSN")
ENV = os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev"
if SENTRY_DSN and ENV not in ("dev", "development", "test", "testing", "local"):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FastApiIntegration(), LoggingIntegration(level=None, event_level=None)],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
            environment=ENV,
            send_default_pii=False,
        )
        log.info("[startup] Sentry initialized for env=%s", ENV)
    except Exception as se:
        log.warning("[startup] Sentry init failed: %s", se)
else:
    log.info("[startup] Sentry disabled (missing DSN or dev/test env)")

# --- Build App ---
app = FastAPI(title="Podcast Pro Plus API")

# Respect X-Forwarded-* headers from Cloud Run / reverse proxies so generated absolute
# URLs (e.g., request.url_for in OAuth flows) use the correct https scheme and host.
if ProxyHeadersMiddleware is not None:
    # Use proxy headers if available so request.url_for reflects the external host/scheme
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# --- Pre-warm password hashing so first signup isn't slow ---
try:
    from api.core.security import get_password_hash
    _ = get_password_hash("__warmup__")  # fire once; result discarded
    log.info("[startup] Password hash warmup complete")
except Exception as _warm_err:  # pragma: no cover
    log.warning("[startup] Password hash warmup skipped: %s", _warm_err)

# DB/tables and additive migrations
run_startup_tasks()

# --- Middleware ---
from starlette.middleware.sessions import SessionMiddleware
# In dev/test environments, don't mark the session cookie as Secure and
# relax SameSite so the cookie is sent on the OAuth redirect back from Google.
# In prod, keep SameSite=None + Secure (https_only=True) for cross-site flows.
_IS_DEV = str(ENV).lower() in {"dev", "development", "local", "test", "testing"}
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    session_cookie="ppp_session",
    max_age=60 * 60 * 24 * 14,
    same_site=("lax" if _IS_DEV else "none"),
    https_only=(False if _IS_DEV else True),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    allow_credentials=True,
)

# Global preflight handler to satisfy browser CORS checks on any path.
@app.options("/{path:path}")
def cors_preflight_handler(path: str):
    return Response(status_code=204)

# Security / request-id middleware
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

class ResponseLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        try:
            origin = request.headers.get("origin")
            method = request.method
            path = request.url.path
            log.debug("[CORS-DBG] incoming %s %s origin=%s", method, path, origin)
        except Exception:
            pass
        response = await call_next(request)
        try:
            aco = response.headers.get("access-control-allow-origin")
            acc = response.headers.get("access-control-allow-credentials")
            log.debug("[CORS-DBG] response for %s %s: A-C-A-O=%s A-C-A-C=%s request_id=%s",
                      method, path, aco, acc, response.headers.get("x-request-id"))
        except Exception:
            pass
        return response

app.add_middleware(ResponseLoggingMiddleware)
install_exception_handlers(app)

# Rate limiting (if enabled)
try:
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.errors import RateLimitExceeded
    if not RL_DISABLED and getattr(limiter, "limit", None):
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)

        async def _rate_limit_handler(request, exc):  # type: ignore
            return JSONResponse(status_code=429, content={"detail": "Too many requests"}, headers={"Retry-After": "60"})
        app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore
except Exception:  # pragma: no cover
    pass

# --- Routers ---
try:
    availability = attach_routers(app)
except Exception as e:
    log.exception("attach_routers threw an exception: %s", e)
    availability = {}

def _ensure_users_route_present() -> None:
    # Never crash Cloud Run on missing router; install a minimal 401 fallback so the app can bind PORT.
    paths = {getattr(r, "path", None) for r in app.routes if getattr(r, "path", None)}
    has_users_me = ("/users/me" in paths) or ("/api/users/me" in paths)
    if not has_users_me:
        log.error("Users router not detected at startup; installing fallback /api/users/me -> 401")
        @app.get("/api/users/me")
        async def __fallback_users_me():
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

# If attach_routers reported availability, heed it; otherwise inspect routes.
if not availability.get("users", False):
    _ensure_users_route_present()

# --- Health Checks ---
@app.get("/api/health")
def api_health_alias():
    return {"status": "ok"}

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/readyz")
def readyz():
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# --- Static Files & SPA ---
STATIC_UI_DIR = Path(os.getenv("STATIC_UI_DIR", "/app/static_ui"))
app.mount("/static/final",   StaticFiles(directory=str(FINAL_DIR),   check_dir=False), name="final")
app.mount("/static/media",   StaticFiles(directory=str(MEDIA_DIR),   check_dir=False), name="media")
app.mount("/static/flubber", StaticFiles(directory=str(FLUBBER_CTX_DIR), check_dir=False), name="flubber")

@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    if full_path.startswith(("api/", "static/")):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    try:
        candidate = STATIC_UI_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_UI_DIR / "index.html"
        if index.exists():
            return FileResponse(index, media_type="text/html")
    except Exception:
        pass
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

__all__ = ["app", "_compute_pt_expiry"]
