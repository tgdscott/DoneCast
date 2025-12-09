"""Backend API package.

This package intentionally does not implement any import aliasing logic.

Canonical imports should use the ``backend.api`` prefix. For convenience and
to preserve backwards compatibility with older code and tests, the top-level
``api`` package provides a meta path alias that forwards ``api.*`` imports to
``backend.api.*``. Keeping the aliasing in a single place avoids confusing
importlib state and, most importantly, prevents executing model modules twice
under different names (which would register duplicate SQLModel tables).
"""

# Do not add any import-time side effects here.

# Provide lazy access to subpackages for compatibility with tests that monkeypatch
# using dotted paths like "api.services.transcription..." without performing an
# explicit import first.
import importlib


def __getattr__(name):  # pragma: no cover - simple import shim
	if name == "services":
		return importlib.import_module(f"{__name__}.services")
	raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


