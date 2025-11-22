"""Routes handling Google OAuth flows."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from api.core import crud
from api.core.config import settings
from urllib.parse import urlparse, urlunparse
from api.core.database import get_session
from api.models.settings import load_admin_settings
from api.models.user import User, UserCreate

# Check if verification module is available
try:
    from api.models.verification import EmailVerification
    VERIFICATION_AVAILABLE = True
except ImportError:
    VERIFICATION_AVAILABLE = False

from .utils import (
    AUTHLIB_ERROR,
    build_oauth_client,
    create_access_token,
    external_base_url,
    is_admin_email,
)

router = APIRouter()
log = logging.getLogger(__name__)


FRONTEND_BASE_SESSION_KEY = "oauth_frontend_base"
FRONTEND_PATH_SESSION_KEY = "oauth_frontend_path"


def _normalize_frontend_base(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
        scheme = (parsed.scheme or "").lower()
        netloc = parsed.netloc
        if not netloc and parsed.path and '://' not in candidate:
            netloc = parsed.path
            if ':' in netloc or netloc.startswith(('localhost', '127.', '0.0.0.0')):
                scheme = scheme or 'http'
        if not scheme:
            scheme = 'https'
        if scheme not in ("http", "https"):
            return None
        if not netloc:
            return None
        host = parsed.hostname or netloc.split(':', 1)[0]
        host_lower = (host or '').lower()
        allowed = False
        if host_lower in {'localhost'}:
            allowed = True
        else:
            try:
                import ipaddress as _ip

                ip = _ip.ip_address(host_lower)
                allowed = ip.is_loopback or ip.is_private
            except Exception:
                if host_lower.endswith(('podcastplusplus.com', 'getpodcastplus.com')) or host_lower.endswith('.local'):
                    allowed = True
        if not allowed:
            return None
        return f"{scheme}://{netloc}".rstrip('/')
    except Exception:
        return None


@router.get("/login/google")
async def login_google(request: Request):
    """Redirect the user to Google's login page."""

    try:
        base = external_base_url(request)
        redirect_uri = f"{base}/api/auth/google/callback"
    except Exception:
        backend_base = settings.OAUTH_BACKEND_BASE or "https://api.podcastplusplus.com"
        redirect_uri = f"{backend_base.rstrip('/')}/api/auth/google/callback"

    # In local dev with a frontend proxy (Vite on :5173) the dynamic base may resolve
    # to 127.0.0.1:5173, while the Google Console is typically configured with
    # http://127.0.0.1:8000/api/auth/google/callback. That mismatch produces a
    # "redirect_uri_mismatch" error after the user selects an account. If the operator
    # has provided OAUTH_BACKEND_BASE or GOOGLE_REDIRECT_URI, prefer that host:port
    # when it differs from the computed base AND both are loopback/local. This keeps
    # production behavior (public domains) unaffected while smoothing local dev.
    try:
        import urllib.parse as _urlp
        configured_redirect = (getattr(settings, 'GOOGLE_REDIRECT_URI', '') or '').strip()
        backend_base = (settings.OAUTH_BACKEND_BASE or '').strip()
        # Normalize configured redirect host
        configured_host = None
        if configured_redirect.endswith('/api/auth/google/callback'):
            parsed_conf = _urlp.urlparse(configured_redirect)
            if parsed_conf.scheme and parsed_conf.netloc:
                configured_host = f"{parsed_conf.scheme}://{parsed_conf.netloc}".rstrip('/')
        elif backend_base:
            # Fall back to backend base if explicit redirect isn't set
            parsed_bb = _urlp.urlparse(backend_base)
            if parsed_bb.scheme and parsed_bb.netloc:
                configured_host = f"{parsed_bb.scheme}://{parsed_bb.netloc}".rstrip('/')
        if configured_host:
            dyn_parsed = _urlp.urlparse(redirect_uri)
            dyn_host = f"{dyn_parsed.scheme}://{dyn_parsed.netloc}".rstrip('/') if dyn_parsed.scheme and dyn_parsed.netloc else None
            def _is_local_host(h: str | None) -> bool:
                if not h:
                    return False
                name = h.split('://',1)[-1].split(':',1)[0]
                if name in {'localhost', '127.0.0.1', '0.0.0.0'}:
                    return True
                try:
                    import ipaddress as _ip
                    return _ip.ip_address(name).is_loopback
                except Exception:
                    return False
            if dyn_host and dyn_host != configured_host and _is_local_host(dyn_host) and _is_local_host(configured_host):
                redirect_uri = f"{configured_host}/api/auth/google/callback"
    except Exception:  # pragma: no cover - defensive path
        pass

    dry_run = request.query_params.get("dry_run") or request.query_params.get("debug")
    frontend_hint = request.query_params.get("return_to") or request.query_params.get("redirect_to")
    # Optional deep-link path to restore after OAuth (relative path only)
    raw_path = request.query_params.get("return_path") or ""
    if not frontend_hint:
        frontend_hint = request.headers.get("origin") or ""
    if not frontend_hint:
        referer = request.headers.get("referer") or request.headers.get("referrer")
        if referer:
            frontend_hint = referer
    normalized_hint = _normalize_frontend_base(frontend_hint)
    try:
        if normalized_hint:
            request.session[FRONTEND_BASE_SESSION_KEY] = normalized_hint
        else:
            request.session.pop(FRONTEND_BASE_SESSION_KEY, None)
        # Store sanitized path if provided (avoid open redirect by forcing leading slash and stripping scheme/host)
        if raw_path:
            from urllib.parse import urlparse as _up
            if len(raw_path) > 512:
                raw_path = raw_path[:512]
            # If the path accidentally includes full URL, extract path+query
            if '://' in raw_path:
                try:
                    parsed_rp = _up(raw_path)
                    rp_candidate = (parsed_rp.path or '/') + (f"?{parsed_rp.query}" if parsed_rp.query else '')
                    raw_path = rp_candidate
                except Exception:
                    raw_path = '/'
            if not raw_path.startswith('/'):
                raw_path = '/' + raw_path.split('/',1)[-1]
            if '\r' in raw_path or '\n' in raw_path:
                raw_path = '/'
            request.session[FRONTEND_PATH_SESSION_KEY] = raw_path
        else:
            request.session.pop(FRONTEND_PATH_SESSION_KEY, None)
    except Exception:
        pass

    if dry_run and str(dry_run).lower() not in {"0", "false", "no"}:
        hdr = request.headers
        return {
            "status": "ok",
            "redirect_uri": redirect_uri,
            "request_url": str(request.url),
            "base_url": str(request.base_url),
            "host": hdr.get("host"),
            "x_forwarded_host": hdr.get("x-forwarded-host"),
            "x_forwarded_proto": hdr.get("x-forwarded-proto"),
            "forwarded": hdr.get("forwarded"),
            "oauth_backend_base": settings.OAUTH_BACKEND_BASE or "",
        }
    
    # Try to get OAuth client with retry logic for network timeouts
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            oauth_client, _ = build_oauth_client()
            client = getattr(oauth_client, "google", None)
            if client is None:
                raise HTTPException(status_code=500, detail="OAuth client not configured")
            
            # Attempt to authorize redirect (this triggers metadata fetch on first call)
            return await client.authorize_redirect(request, redirect_uri)
            
        except RuntimeError as exc:
            # Configuration error, don't retry
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google login is temporarily unavailable. Please contact support.",
            ) from exc
        except HTTPException:
            # Re-raise HTTPExceptions directly
            raise
        except Exception as exc:
            # Check if it's a timeout error
            exc_str = str(type(exc).__name__) + str(exc)
            is_timeout = "timeout" in exc_str.lower() or "ConnectTimeout" in str(type(exc).__name__)
            
            if is_timeout and attempt < max_retries:
                log.warning(
                    "OAuth: Network timeout on attempt %d/%d, retrying...",
                    attempt + 1,
                    max_retries + 1
                )
                # Clear cache to force fresh connection on retry
                import api.routers.auth.utils as auth_utils
                auth_utils._oauth_client_cache = None
                continue
            
            # Final attempt failed or non-timeout error
            log.exception("OAuth: Failed to initiate Google login after %d attempts", attempt + 1)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to connect to Google login service. Please try again in a moment.",
            ) from exc


@router.get("/google/callback")
async def auth_google_callback(request: Request, db_session: Session = Depends(get_session)):
    """Handle the callback from Google, create/update the user, and redirect."""

    try:
        oauth_client, _ = build_oauth_client()
    except RuntimeError as exc:
        log.exception("Google OAuth unavailable during callback")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is temporarily unavailable. Please contact support.",
        ) from exc

    try:
        client = getattr(oauth_client, "google", None)
        if client is None:
            raise RuntimeError("OAuth client not configured")
        token: Mapping[str, Any] | None = await client.authorize_access_token(request)
    except Exception as exc:
        log.exception("Google OAuth token exchange failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate Google credentials: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not isinstance(token, Mapping):
        log.error("Google OAuth returned unexpected token payload type: %s", type(token))
        raise HTTPException(status_code=400, detail="Could not fetch user info from Google.")

    client = getattr(oauth_client, "google", None)
    google_user_data = token.get("userinfo")
    if not isinstance(google_user_data, Mapping) or "email" not in google_user_data:
        google_user_data = None
        id_token = token.get("id_token")
        if id_token and client is not None:
            try:
                google_user_data = await client.parse_id_token(request, token)
            except Exception as parse_err:
                log.warning("Failed to parse Google ID token: %s", parse_err)
        if not google_user_data and client is not None:
            try:
                google_user_data = await client.userinfo(token=token)
            except Exception as userinfo_err:
                log.warning("Failed to fetch Google userinfo: %s", userinfo_err)

    if not isinstance(google_user_data, Mapping) or "email" not in google_user_data:
        raise HTTPException(status_code=400, detail="Could not fetch user info from Google.")

    user_email = str(google_user_data["email"])
    google_user_id = str(google_user_data.get("sub") or google_user_data.get("id") or "").strip() or None

    if not google_user_id:
        log.warning("Google userinfo missing stable subject identifier for email %s", user_email)

    try:
        user = crud.get_user_by_email(session=db_session, email=user_email)

        if not user:
            user_create = UserCreate(
                email=user_email,
                password=str(uuid4()),
                google_id=google_user_id,
            )
            try:
                admin_settings = load_admin_settings(db_session)
                user_create.is_active = bool(getattr(admin_settings, "default_user_active", True))
                user_create.tier = getattr(admin_settings, "default_user_tier", "trial")
            except Exception:
                user_create.is_active = True
                user_create.tier = "trial"  # All accounts start as trial
            user = crud.create_user(session=db_session, user_create=user_create)

        if is_admin_email(user.email):
            user.is_admin = True

        if google_user_id and not user.google_id:
            user.google_id = google_user_id

        # Auto-verify email for Google OAuth users
        # Google users don't need email verification since Google already verified their email
        if google_user_id and VERIFICATION_AVAILABLE:
            from sqlmodel import select
            
            # Check if user already has a verified email
            existing_verification = db_session.exec(
                select(EmailVerification)
                .where(
                    EmailVerification.user_id == user.id,
                    EmailVerification.verified_at != None  # noqa: E711
                )
                .limit(1)
            ).first()
            
            # If no verified email exists, create one
            if not existing_verification:
                now = datetime.utcnow()
                verification = EmailVerification(
                    user_id=user.id,
                    code="GOOGLE-OAUTH",
                    jwt_token=None,
                    expires_at=now,  # Already expired since it's pre-verified
                    verified_at=now,  # Mark as verified immediately
                    used=True,  # Mark as used
                    created_at=now,
                )
                db_session.add(verification)
                log.info(f"[OAUTH] Auto-verified email for Google user {user.email}")

        user.last_login = datetime.utcnow()
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    except Exception as db_exc:  # pragma: no cover - defensive logging path
        # Common root causes observed in production: transient Cloud SQL connectivity
        # issues or missing DATABASE_URL configuration during cold starts. We do not
        # surface raw DB errors to the browser (which would 500 the OAuth popup and
        # confuse users); instead return a 503 so the frontend can retry gracefully.
        log.exception("Google OAuth callback failed while persisting user '%s'", user_email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable (database). Please retry in a moment.",
        ) from db_exc

    access_token = create_access_token({"sub": user.email})

    try:
        session_frontend_base = request.session.pop(FRONTEND_BASE_SESSION_KEY, None)
    except Exception:
        session_frontend_base = None
    try:
        session_frontend_path = request.session.pop(FRONTEND_PATH_SESSION_KEY, None)
    except Exception:
        session_frontend_path = None

    # Prefer any loopback/private base we captured during the login redirect
    # (e.g., http://127.0.0.1:5173 while running Vite). This keeps local dev
    # flows from being forced back to the production APP_BASE_URL.
    frontend_base = (session_frontend_base or "").strip()
    if not frontend_base:
        frontend_base = (settings.APP_BASE_URL or "").strip()
    if not frontend_base:
        try:
            from api.routers.auth.utils import external_base_url as _ext

            base = _ext(request)
            parsed = urlparse(base)
            scheme = parsed.scheme or "https"
            netloc = parsed.netloc or ""
            host = parsed.hostname or ""
            port = parsed.port
            trusted_suffixes = ("podcastplusplus.com", "getpodcastplus.com")
            trimmed_host = host
            if host and host.lower().endswith(trusted_suffixes):
                for pref in ("app.", "api.", "dashboard.", "backend."):
                    if trimmed_host.lower().startswith(pref):
                        trimmed_host = trimmed_host[len(pref):]
                        break
            if trimmed_host:
                if port and port not in (80, 443):
                    netloc_out = f"{trimmed_host}:{port}"
                else:
                    netloc_out = trimmed_host
            else:
                netloc_out = netloc or host
            if not netloc_out:
                raise ValueError("frontend netloc missing")
            frontend_base = urlunparse((scheme, netloc_out, "", "", "", ""))
        except Exception:
            frontend_base = "https://podcastplusplus.com"
    frontend_base = frontend_base.rstrip("/")
    # Prefer landing users inside the app area immediately after OAuth instead of
    # dropping them on the marketing page. Admins still go to /admin, regular
    # users to /dashboard. Hash fragment preserves existing token capture logic.
    if session_frontend_path and isinstance(session_frontend_path, str) and session_frontend_path.startswith('/'):
        target_path = session_frontend_path
    else:
        if user.is_admin:
            target_path = "/admin"
        else:
            target_path = "/dashboard"
    # Append access token as hash fragment preserving any existing fragment
    # Ensure we append the token as a single fragment. Previous logic produced a
    # double '##' when target_path lacked an existing hash (e.g. /dashboard##access_token=...)
    # which broke frontend token extraction (became key name '#access_token').
    if '#' in target_path:
        # target_path already contains a fragment; append using '&'
        base_out = f"{frontend_base}{target_path}"
        if base_out.endswith('#'):
            # Degenerate case: fragment marker present but empty
            frontend_url = f"{base_out}access_token={access_token}&token_type=bearer"
        else:
            join_char = '&' if not base_out.endswith(('&', '?')) else ''
            frontend_url = f"{base_out}{join_char}access_token={access_token}&token_type=bearer"
    else:
        frontend_url = f"{frontend_base}{target_path}#access_token={access_token}&token_type=bearer"

    return RedirectResponse(url=frontend_url)


@router.get("/debug/google-client", include_in_schema=False)
async def debug_google_client(request: Request):
    """Reveals what Google client settings are active."""

    def _mask(val: str | None) -> str:
        value = (val or "").strip()
        return (value[:8] + "…" if len(value) > 8 else value) if value else ""

    backend_base = settings.OAUTH_BACKEND_BASE or "https://api.podcastplusplus.com"
    try:
        dynamic_redirect = f"{external_base_url(request)}/api/auth/google/callback"
    except Exception:
        dynamic_redirect = f"{backend_base}/api/auth/google/callback"
    hdr = request.headers
    try:
        _client, _cid = build_oauth_client()
        oauth_client_registration_ok = True
        oauth_client_error = ""
    except Exception as exc:
        oauth_client_registration_ok = False
        oauth_client_error = str(exc)
    return {
        "client_id_hint": _mask(settings.GOOGLE_CLIENT_ID),
        "client_secret_hint": _mask(getattr(settings, "GOOGLE_CLIENT_SECRET", None)),
        "client_secret_set": bool(getattr(settings, "GOOGLE_CLIENT_SECRET", None)),
        "redirect_uri": f"{backend_base}/api/auth/google/callback",
        "redirect_uri_dynamic": dynamic_redirect,
        "request_host": hdr.get("host"),
        "x_forwarded_host": hdr.get("x-forwarded-host"),
        "x_forwarded_proto": hdr.get("x-forwarded-proto"),
        "forwarded": hdr.get("forwarded"),
        "oauth_backend_base_is_set": bool(settings.OAUTH_BACKEND_BASE),
        "authlib_available": AUTHLIB_ERROR is None,
        "authlib_error": str(AUTHLIB_ERROR) if AUTHLIB_ERROR else "",
        "oauth_client_registration_ok": oauth_client_registration_ok,
        "oauth_client_registration_error": oauth_client_error,
    }
