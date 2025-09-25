"""
Legacy shim for `api.routers.episodes`.

This module dynamically loads and proxies to the package implementation in
`api/routers/episodes/__init__.py` so imports keep working even though the
implementation moved to a package. This avoids circular self-imports and
ensures callers get the real `router` from the package aggregator.
"""

import importlib.util
import os
import sys
from types import ModuleType


def _load_pkg_module(module_name: str, init_path: str) -> ModuleType:
	pkg_dir = os.path.dirname(init_path)
	# Mark as a package via submodule_search_locations so relative imports work
	spec = importlib.util.spec_from_file_location(
		module_name, init_path, submodule_search_locations=[pkg_dir]
	)
	if spec is None or spec.loader is None:
		raise ImportError(f"Cannot load spec for {module_name} from {init_path}")
	module = importlib.util.module_from_spec(spec)
	# Set package attributes
	module.__package__ = module_name
	if getattr(module, "__path__", None) is None:
		module.__path__ = [pkg_dir]  # type: ignore[attr-defined]
	# Replace this shim in sys.modules with the real package module
	sys.modules[module_name] = module
	spec.loader.exec_module(module)  # type: ignore[assignment]
	return module


_MODULE_NAME = __name__  # 'api.routers.episodes'
_INIT_PATH = os.path.join(os.path.dirname(__file__), 'episodes', '__init__.py')
_pkg = _load_pkg_module(_MODULE_NAME, _INIT_PATH)

# Re-export public API
router = getattr(_pkg, 'router', None)

__all__ = ['router']
