from __future__ import annotations

import importlib
import logging
from typing import Iterable, Tuple

from fastapi import APIRouter

log = logging.getLogger("ppp.episodes")


# Aggregator router: parent provides '/episodes' prefix
router = APIRouter(prefix="/episodes", tags=["episodes"])


def _load_router(module: str, required: bool) -> APIRouter | None:
    """Import a sibling module and return its FastAPI router.

    Some episode subrouters depend on optional runtime components (for example
    the Celery worker package). In production those modules are present, but in
    lightweight or diagnostics deployments they may be intentionally absent.
    Previously a missing optional dependency raised during import which aborted
    the entire episodes router registration, leading to 404/405 responses for
    *every* episode endpoint. By importing defensively we keep the critical
    read/write/assemble routes online even when ancillary modules are missing.
    """

    try:
        module_obj = importlib.import_module(f".{module}", package=__name__)
    except Exception as exc:
        if required:
            raise
        log.warning("episodes router optional module '%s' unavailable: %s", module, exc)
        log.debug("episodes router import failure", exc_info=True)
        return None

    router_obj = getattr(module_obj, "router", None)
    if router_obj is None:
        message = f"episodes router module '{module}' does not export 'router'"
        if required:
            raise AttributeError(message)
        log.warning(message)
        return None

    return router_obj


_ROUTER_IMPORTS: Iterable[Tuple[str, bool]] = (
    ("assemble", True),
    ("precheck", True),
    ("read", True),
    ("write", True),
    ("publish", True),
    ("jobs", False),
    ("edit", False),
    ("retry", False),
)


loaded_routers: list[APIRouter] = []
for module_name, required in _ROUTER_IMPORTS:
    try:
        maybe_router = _load_router(module_name, required=required)
    except Exception as exc:
        log.exception("Failed to load required episodes router '%s'", module_name)
        raise
    if maybe_router is not None:
        loaded_routers.append(maybe_router)


# Register the assemble router before the generic read/write routers so the
# static path (/episodes/assemble) is not shadowed by parameterised routes such
# as /episodes/{episode_id}. FastAPI normally prefers static routes, but the
# import order becomes important when routers are dynamically attached during
# runtime startup. By including the assemble router first we ensure POST
# requests hit the intended handler instead of returning an unexpected 405.
for sub_router in loaded_routers:
    router.include_router(sub_router)


__all__ = ["router"]
