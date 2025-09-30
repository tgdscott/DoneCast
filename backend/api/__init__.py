"""Backend API package with symmetric import aliasing.

This package may be imported in two different ways depending on sys.path order:

- As ``backend.api`` (canonical when importing from project root), or
- As ``api`` (when the ``backend/`` folder is added to sys.path, as done in tests).

If both names import the same files separately, Python will execute module code
twice under two different module names. For SQLModel models, that creates
duplicate table registrations (e.g., "Table 'user' is already defined").

To avoid this, we install a tiny aliasing layer that ensures both import paths
refer to the exact same module objects without re-executing code:

1) We register the current package under the alternative name in sys.modules.
2) We install a MetaPathFinder that, whenever a submodule is imported via the
   alternative prefix, imports the canonical module first (if needed) and then
   returns an alias module spec that reuses the existing module object.

This keeps a single execution path and prevents duplicate SQLAlchemy/SQLModel
table definitions during test collection.
"""

from __future__ import annotations

from importlib import import_module
from importlib import util as importlib_util
from importlib import abc as importlib_abc
from types import ModuleType
from typing import Optional, Sequence
import sys


_THIS_NAME = __name__  # either 'backend.api' or 'api'


def _canon_and_alt() -> tuple[str, str]:
	"""Return (canonical_prefix, alternate_prefix) based on how we're loaded."""
	if _THIS_NAME == "api":
		return ("api", "backend.api")
	return ("backend.api", "api")


_CANON_ROOT, _ALT_ROOT = _canon_and_alt()


# 1) Root package aliasing: ensure both names point to the same package object
this_pkg: ModuleType = sys.modules[_THIS_NAME]
sys.modules.setdefault(_CANON_ROOT, this_pkg)
sys.modules.setdefault(_ALT_ROOT, this_pkg)


class _SymmetricAliasLoader(importlib_abc.Loader):
	"""Loader that aliases an alternate module name to an existing canonical one."""

	def __init__(self, fullname: str, canon_name: str) -> None:
		self.fullname = fullname
		self.canon_name = canon_name

	def create_module(self, spec):  # type: ignore[override]
		# Reuse the already-imported canonical module object.
		mod = sys.modules.get(self.canon_name)
		if mod is None:
			# Import it if not present; this executes code only once under canon name.
			mod = import_module(self.canon_name)
		# Also register under the alternate fullname
		sys.modules[self.fullname] = mod
		return mod

	def exec_module(self, module):  # type: ignore[override]
		# Nothing to execute; we're aliasing an existing module.
		return None


class _SymmetricAliasFinder(importlib_abc.MetaPathFinder):
	"""Map alternate prefix imports to the canonical ones without re-executing code."""

	def __init__(self, canon_root: str, alt_root: str) -> None:
		self.canon_root = canon_root
		self.alt_root = alt_root
		self.alt_prefix = f"{alt_root}."
		self.canon_prefix = f"{canon_root}."

	def find_spec(self, fullname: str, path: Optional[Sequence[str]] = None, target=None):  # type: ignore[override]
		# Only alias submodules, not the root package itself
		if fullname == self.alt_root or not fullname.startswith(self.alt_prefix):
			return None

		# Compute the corresponding canonical module name
		suffix = fullname[len(self.alt_prefix):]
		canon_name = f"{self.canon_root}.{suffix}"

		# If the canonical module is already imported (or importable), create an alias spec
		# Try to find spec for canonical name to determine if it's importable
		canon_spec = importlib_util.find_spec(canon_name)
		if canon_spec is None:
			# If canonical isn't importable, do nothing; let normal import machinery handle it
			return None

		loader = _SymmetricAliasLoader(fullname, canon_name)
		alias_spec = importlib_util.spec_from_loader(fullname, loader, is_package=(canon_spec.submodule_search_locations is not None))
		if alias_spec and canon_spec.submodule_search_locations is not None:
			alias_spec.submodule_search_locations = list(canon_spec.submodule_search_locations)
		return alias_spec


# 2) Install the finder once to guarantee symmetric aliasing for submodules
_finder = _SymmetricAliasFinder(_CANON_ROOT, _ALT_ROOT)
if _finder not in sys.meta_path:
	# Put it near the front so it takes precedence
	sys.meta_path.insert(0, _finder)

