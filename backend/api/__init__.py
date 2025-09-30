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


