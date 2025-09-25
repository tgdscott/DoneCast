from __future__ import annotations

"""Constants for clean_engine features.

Kept lightweight; adjust values as needed. Intentionally not auto-imported by
features.__init__ to avoid changing public API surface unexpectedly.
"""

# Default silence detection parameters (ms/db).
DEFAULT_MIN_SILENCE_MS = 300
DEFAULT_SILENCE_DBFS_OFFSET = -20

# Default filler trimming (ms).
DEFAULT_FILLER_LEAD_TRIM_MS = 40
DEFAULT_FILLER_TAIL_TRIM_MS = 40
