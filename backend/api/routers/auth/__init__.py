"""Authentication router package aggregating credential, verification, OAuth and policy flows."""

from __future__ import annotations

from fastapi import APIRouter

from . import credentials, oauth, terms, verification
from .utils import (
    AUTHLIB_ERROR,
    JOSE_IMPORT_ERROR,
    RL_DISABLED,
    build_oauth_client,
    create_access_token,
    external_base_url,
    get_current_user,
    is_admin_email,
    limiter,
    oauth2_scheme,
    parse_forwarded_header,
    raise_jwt_missing,
    to_user_public,
    verify_password_or_error,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

for subrouter in (credentials.router, verification.router, oauth.router, terms.router):
    router.include_router(subrouter, tags=["Authentication"])

__all__ = [
    "AUTHLIB_ERROR",
    "JOSE_IMPORT_ERROR",
    "RL_DISABLED",
    "build_oauth_client",
    "create_access_token",
    "external_base_url",
    "get_current_user",
    "is_admin_email",
    "limiter",
    "oauth2_scheme",
    "parse_forwarded_header",
    "raise_jwt_missing",
    "router",
    "to_user_public",
    "verify_password_or_error",
]
