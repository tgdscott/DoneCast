"""Compatibility alias exposing :mod:`backend.infrastructure` to API modules.

Historically the application imported infrastructure helpers via
``backend.api.infrastructure`` or ``api.infrastructure`` paths. The actual
implementations now live in :mod:`backend.infrastructure`. Importing those
modules under multiple names caused ``ModuleNotFoundError`` once we reorganised
packages. This module reinstates the alias while guaranteeing that the canonical
``backend.infrastructure`` modules are only initialised once.
"""

from __future__ import annotations

from importlib import abc as importlib_abc
from importlib import import_module
from importlib import util as importlib_util
from types import ModuleType
from typing import Iterable
import sys


_BACKEND_PACKAGE_NAME = "backend.infrastructure"
_backend_pkg: ModuleType = import_module(_BACKEND_PACKAGE_NAME)


def __getattr__(name: str) -> object:
    """Proxy attribute access to :mod:`backend.infrastructure` lazily."""

    alias_fq = f"{__name__}.{name}"
    if alias_fq in sys.modules:
        return sys.modules[alias_fq]

    try:
        import_module(alias_fq)
        if alias_fq in sys.modules:
            return sys.modules[alias_fq]
    except Exception:
        pass

    return getattr(_backend_pkg, name)


def __dir__() -> Iterable[str]:
    return dir(_backend_pkg)


if hasattr(_backend_pkg, "__all__"):
    __all__ = list(getattr(_backend_pkg, "__all__"))  # type: ignore[assignment]

if hasattr(_backend_pkg, "__path__"):
    __path__ = list(getattr(_backend_pkg, "__path__"))  # type: ignore[assignment]


class _InfrastructureAliasLoader(importlib_abc.Loader):
    """Alias ``backend.api.infrastructure.*`` modules to ``backend.infrastructure``."""

    def __init__(self, fullname: str, backend_name: str, is_package: bool) -> None:
        self.fullname = fullname
        self.backend_name = backend_name
        self.is_package = is_package

    def create_module(self, spec):  # type: ignore[override]
        backend_mod = import_module(self.backend_name)
        sys.modules[self.fullname] = backend_mod
        return backend_mod

    def exec_module(self, module):  # type: ignore[override]
        return None


class _InfrastructureAliasFinder(importlib_abc.MetaPathFinder):
    """Redirect ``backend.api.infrastructure.*`` to ``backend.infrastructure.*``."""

    _prefix = f"{__name__}."

    def find_spec(self, fullname, path, target=None):  # type: ignore[override]
        if not fullname.startswith(self._prefix):
            return None

        backend_name = fullname.replace(__name__, _BACKEND_PACKAGE_NAME, 1)
        backend_spec = importlib_util.find_spec(backend_name)
        if backend_spec is None:
            return None

        is_package = backend_spec.submodule_search_locations is not None
        loader = _InfrastructureAliasLoader(fullname, backend_name, is_package)
        alias_spec = importlib_util.spec_from_loader(fullname, loader, is_package=is_package)
        if (
            alias_spec
            and is_package
            and backend_spec.submodule_search_locations is not None
        ):
            alias_spec.submodule_search_locations = list(
                backend_spec.submodule_search_locations
            )
        return alias_spec


_finder = _InfrastructureAliasFinder()
if _finder not in sys.meta_path:
    sys.meta_path.insert(0, _finder)
