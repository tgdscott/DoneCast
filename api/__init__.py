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
from importlib import util as importlib_util
from importlib import abc as importlib_abc
from types import ModuleType
from typing import Iterable

import sys


_BACKEND_PACKAGE_NAME = "backend.api"

# Import the actual backend package once so we can delegate attribute lookups
# and mirror its path. Importing the package (whose __init__ is empty) is safe
# and does not execute application startup code.
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


# IMPORTANT: Install the meta path finder BEFORE importing/aliasing any
# submodules. This prevents executing backend model modules twice under
# different names during import cascades (which would register duplicate
# SQLModel tables and crash with "Table 'user' is already defined").


class _BackendAliasLoader(importlib_abc.Loader):
    """Alias ``api.*`` modules to the canonical ``backend.api.*`` modules.

    Instead of creating a proxy wrapper module, we register the alias name in
    ``sys.modules`` to point directly at the already-imported backend module
    object. This guarantees a single set of module globals and allows tests to
    monkeypatch module-level variables (e.g., ``_HTTPX_AVAILABLE``) via either
    import path.
    """

    def __init__(self, fullname: str, backend_name: str, is_package: bool) -> None:
        self.fullname = fullname
        self.backend_name = backend_name
        self.is_package = is_package

    def create_module(self, spec):  # type: ignore[override]
        # Import (or retrieve) the canonical backend module, then register it
        # under the alias name as well so both entries reference the same object.
        backend_mod = import_module(self.backend_name)
        sys.modules[self.fullname] = backend_mod
        return backend_mod

    def exec_module(self, module):  # type: ignore[override]
        # Nothing to execute; we've aliased to the canonical module object.
        return None


class _BackendAliasFinder(importlib_abc.MetaPathFinder):
    """Redirect ``api.*`` imports to the matching ``backend.api.*`` module."""

    _prefix = f"{__name__}."

    def find_spec(self, fullname, path, target=None):  # type: ignore[override]
        if not fullname.startswith(self._prefix):
            return None

        backend_name = fullname.replace(__name__, _BACKEND_PACKAGE_NAME, 1)
        backend_spec = importlib_util.find_spec(backend_name)
        if backend_spec is None:
            return None

        is_package = backend_spec.submodule_search_locations is not None
        loader = _BackendAliasLoader(fullname, backend_name, is_package)
        alias_spec = importlib_util.spec_from_loader(fullname, loader, is_package=is_package)
        if alias_spec and is_package and backend_spec.submodule_search_locations is not None:
            alias_spec.submodule_search_locations = list(backend_spec.submodule_search_locations)
        return alias_spec


# Install the alias finder ahead of the default path finder so submodule imports
# (e.g. ``import api.models.podcast``) reuse the already imported backend
# modules instead of executing them twice under a new name.
_finder = _BackendAliasFinder()
if _finder not in sys.meta_path:
    sys.meta_path.insert(0, _finder)


## Note: We intentionally avoid symmetrical aliasing (backend.api.* -> api.*).
## Keeping a single canonical execution path (backend.api.*) and redirecting
## only api.* imports to it is sufficient and avoids confusing __spec__ state.


# Do not proactively import submodules here. The MetaPathFinder/Loader will
# lazily alias requests like ``import api.models.user`` to the canonical
# ``backend.api.models.user`` module, ensuring the code is executed exactly once.


## (finders installed earlier; see above)

