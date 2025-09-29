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
from api.core.database import get_session
from api.models.settings import load_admin_settings
from api.models.user import User, UserCreate

from .utils import (
    AUTHLIB_ERROR,
    build_oauth_client,
    create_access_token,
    external_base_url,
    is_admin_email,
)

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/login/google")
async def login_google(request: Request):
    """Redirect the user to Google's login page."""

    try:
        base = external_base_url(request)
        redirect_uri = f"{base}/api/auth/google/callback"
    except Exception:
        backend_base = settings.OAUTH_BACKEND_BASE or "https://api.podcastplusplus.com"
        redirect_uri = f"{backend_base.rstrip('/')}/api/auth/google/callback"

    dry_run = request.query_params.get("dry_run") or request.query_params.get("debug")
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
    try:
        oauth_client, _ = build_oauth_client()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is temporarily unavailable. Please contact support.",
        ) from exc
    client = getattr(oauth_client, "google", None)
    if client is None:
        raise HTTPException(status_code=500, detail="OAuth client not configured")
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def auth_google_callback(request: Request, session: Session = Depends(get_session)):
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
        if id_token:
            try:
                google_user_data = await client.parse_id_token(request, token)
            except Exception as parse_err:
                log.warning("Failed to parse Google ID token: %s", parse_err)
        if not google_user_data:
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

    user = crud.get_user_by_email(session=session, email=user_email)

    if not user:
        user_create = UserCreate(
            email=user_email,
            password=str(uuid4()),
            google_id=google_user_id,
        )
        try:
            admin_settings = load_admin_settings(session)
            user_create.is_active = bool(getattr(admin_settings, "default_user_active", True))
        except Exception:
            user_create.is_active = True
        user = crud.create_user(session=session, user_create=user_create)

    if is_admin_email(user.email):
        user.is_admin = True

    if google_user_id and not user.google_id:
        user.google_id = google_user_id

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    access_token = create_access_token({"sub": user.email})

    frontend_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    frontend_url = f"{frontend_base}/#access_token={access_token}&token_type=bearer"
    if user.is_admin:
        frontend_url = f"{frontend_base}/admin#access_token={access_token}&token_type=bearer"

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
