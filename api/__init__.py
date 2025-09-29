"""Compatibility package that exposes :mod:`backend.api` as :mod:`api`.

This repository historically imported application modules via the
``backend.api`` package path.  The upstream tests, however, expect the
shorter ``api`` namespace to be available.  To keep the code structure
unchanged while satisfying those imports we forward all attribute and
sub-module lookups to the ``backend.api`` package.

The module exposes ``backend.api``'s public interface transparently and
shares its search path so that ``import api.services.transcription``
works exactly the same as ``import backend.api.services.transcription``.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Iterable

import sys


_BACKEND_PACKAGE_NAME = "backend.api"

# Import the actual backend package once so we can delegate all lookups to it.
_backend_api: ModuleType = import_module(_BACKEND_PACKAGE_NAME)


def __getattr__(name: str) -> object:
    """Proxy attribute access to :mod:`backend.api`."""

    return getattr(_backend_api, name)


def __dir__() -> Iterable[str]:
    """Mirror ``dir()`` from the backend package for introspection."""

    return dir(_backend_api)


# Expose the backend package's ``__all__`` if it defines one.
if hasattr(_backend_api, "__all__"):
    __all__ = list(getattr(_backend_api, "__all__"))  # type: ignore[assignment]


# Share the backend package's path so the import machinery finds submodules.
# ``list(...)`` ensures we copy the value instead of aliasing the original
# ``_NamespacePath`` object, which keeps things stable if the backend mutates
# its search path at runtime.
if hasattr(_backend_api, "__path__"):
    __path__ = list(getattr(_backend_api, "__path__"))  # type: ignore[assignment]


# Register the common alias modules in ``sys.modules`` so imports like
# ``import api.services.transcription`` resolve to ``backend.api.services``
# without extra work from callers.
for submodule in ("core", "routers", "services", "models", "tasks", "middleware", "startup_tasks", "transcription"):
    full_name = f"{_BACKEND_PACKAGE_NAME}.{submodule}"
    try:
        module = import_module(full_name)
    except ModuleNotFoundError:
        continue
    alias = f"{__name__}.{submodule}"
    sys.modules[alias] = module
    setattr(sys.modules[__name__], submodule, module)

