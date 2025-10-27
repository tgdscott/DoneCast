from __future__ import annotations
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
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
from api.core.paths import FINAL_DIR, MEDIA_DIR, FLUBBER_CTX_DIR, INTERN_CTX_DIR

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

# (Deferred) DB/tables and additive migrations now run in a background thread
# to avoid blocking Cloud Run from detecting the listening port.

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
    allow_origin_regex=r"https://(?:[a-z0-9-]+\.)?(?:podcastplusplus\.com|getpodcastplus\.com)",
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    allow_credentials=True,
)

# --- Dev Safety Middleware (Cloud SQL Proxy protection) ---
from api.middleware.dev_safety import dev_read_only_middleware
app.middleware("http")(dev_read_only_middleware)

# --- Deferred Startup Tasks -------------------------------------------------
import threading, time as _time
from pathlib import Path as _Path

def _launch_startup_tasks() -> None:
    """Run additive migrations & housekeeping in background.

    Environment controls:
      SKIP_STARTUP_MIGRATIONS=1 -> skip entirely
      BLOCKING_STARTUP_TASKS=1 or STARTUP_TASKS_MODE=sync -> run inline (legacy behavior)
    """
    skip = (os.getenv("SKIP_STARTUP_MIGRATIONS") or "").lower() in {"1","true","yes","on"}
    mode = (os.getenv("STARTUP_TASKS_MODE") or "async").lower()
    blocking_flag = (os.getenv("BLOCKING_STARTUP_TASKS") or "").lower() in {"1","true","yes","on"}
    sentinel_path = _Path(os.getenv("STARTUP_SENTINEL_PATH", "/tmp/ppp_startup_done"))
    single = (os.getenv("SINGLE_STARTUP_TASKS") or "1").lower() in {"1","true","yes","on"}
    
    # NOTE: Transcript recovery moved into run_startup_tasks() to avoid duplicate execution
    # (was running twice: once here, once in startup_tasks.py)
    
    if skip:
        log.warning("[deferred-startup] SKIP_STARTUP_MIGRATIONS=1 -> skipping run_startup_tasks()")
        return
    if single and sentinel_path.exists():
        log.info("[deferred-startup] Sentinel %s exists -> skipping startup tasks", sentinel_path)
        return
    if blocking_flag or mode == "sync":
        log.info("[deferred-startup] Running startup tasks synchronously (blocking mode)")
        try:
            run_startup_tasks()
            log.info("[deferred-startup] Startup tasks complete (sync)")
            if single:
                try:
                    sentinel_path.write_text(str(int(_time.time())))
                except Exception:
                    pass
        except Exception as e:  # pragma: no cover
            log.exception("[deferred-startup] Startup tasks failed (sync): %s", e)
        return
    def _runner():
        start_ts = _time.time()
        try:
            log.info("[deferred-startup] Background startup tasks begin")
            run_startup_tasks()
            elapsed = _time.time() - start_ts
            log.info("[deferred-startup] Startup tasks complete in %.2fs", elapsed)
            if single:
                try:
                    sentinel_path.write_text(str(int(_time.time())))
                except Exception:
                    pass
        except Exception as e:  # pragma: no cover
            log.exception("[deferred-startup] Startup tasks failed: %s", e)
    try:
        thread = threading.Thread(target=_runner, name="startup-tasks", daemon=True)
        thread.start()
        log.info("[deferred-startup] Launched background thread for startup tasks (thread=%s)", thread.name)
    except Exception as e:  # pragma: no cover
        log.exception("[deferred-startup] Could not launch background startup tasks: %s", e)

@app.on_event("startup")
async def _kickoff_background_startup():  # type: ignore
    _launch_startup_tasks()

# Global preflight handler to satisfy browser CORS checks on any path and
# defensively apply CORS headers even if Starlette's CORSMiddleware misses
# an edge-case (e.g. complex job_id paths, proxies stripping headers, etc.).
@app.options("/{path:path}")
def cors_preflight_handler(path: str, request: Request):  # type: ignore[override]
    origin = request.headers.get("origin") or ""
    requested_headers = request.headers.get("Access-Control-Request-Headers") or request.headers.get("access-control-request-headers")

    # Build a permissive (but restricted to our allowlist / known suffixes) selection.
    allowed_list = settings.cors_allowed_origin_list
    chosen = None
    if origin:
        o = origin.rstrip('/')
        if o in allowed_list:
            chosen = o
        else:
            # Suffix fallback for apex / subdomain variants we trust.
            try:
                from urllib.parse import urlparse
                parsed = urlparse(o)
                host = (parsed.hostname or "").lower()
                if host:
                    for suffix in ("podcastplusplus.com", "getpodcastplus.com"):
                        if host == suffix or host.endswith(f".{suffix}"):
                            chosen = f"{parsed.scheme}://{parsed.netloc}"
                            break
            except Exception:  # pragma: no cover - defensive
                chosen = None

    resp = Response(status_code=204)
    if chosen:
        resp.headers['Access-Control-Allow-Origin'] = chosen
        resp.headers.setdefault('Access-Control-Allow-Credentials', 'true')
        # Make sure caching layers vary on Origin so we don't leak headers
        vary_existing = resp.headers.get('Vary')
        vary_vals = [] if not vary_existing else [v.strip() for v in vary_existing.split(',') if v.strip()]
        for v in ("Origin", "Referer"):
            if v not in vary_vals:
                vary_vals.append(v)
        if vary_vals:
            resp.headers['Vary'] = ", ".join(vary_vals)

    resp.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
    if requested_headers:
        resp.headers['Access-Control-Allow-Headers'] = requested_headers
    else:
        resp.headers.setdefault("Access-Control-Allow-Headers", "*")
    # Short TTL for preflight cache; browsers will revalidate occasionally.
    resp.headers.setdefault("Access-Control-Max-Age", "600")
    return resp

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
app.mount("/static/intern",  StaticFiles(directory=str(INTERN_CTX_DIR),  check_dir=False), name="intern")

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
