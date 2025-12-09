"""Authentication router package aggregating credential, verification, OAuth and policy flows."""

from __future__ import annotations

from fastapi import APIRouter
import logging

log = logging.getLogger(__name__)

# Import submodules defensively so a failure in one doesn't prevent the
# entire `auth` package from importing. If an optional submodule fails
# to import (for example due to a missing env var or optional dependency),
# we log the error and continue to register the remaining auth routes.
_submodules = ["credentials", "verification", "oauth", "terms"]
_imported_subrouters = []
for _name in _submodules:
    try:
        m = __import__(f"{__name__}.{_name}", fromlist=["router"])
        sub = getattr(m, "router", None)
        if sub is not None:
            _imported_subrouters.append(sub)
    except Exception as e:  # pragma: no cover - defensive startup handling
        # Keep startup resilient; log a warning with the module name and brief error
        tb = getattr(e, "__repr__", lambda: repr(e))()
        log.warning("Auth submodule %s failed to import: %s", _name, tb)

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
for subrouter in _imported_subrouters:
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
