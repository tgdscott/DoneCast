"""Audio processing subpackage.

This package contains modularized pieces of the former monolithic
``audio_processor.py`` to improve maintainability and testability.

Imports inside this package pull in heavyweight dependencies (database
settings, model definitions, etc.). To keep import side effects manageable
for lightweight utilities, we lazily proxy access to the main orchestration
entry point instead of importing it eagerly at module load time.
"""

from __future__ import annotations

from typing import Any

__all__ = ["process_and_assemble_episode"]


def process_and_assemble_episode(*args: Any, **kwargs: Any):
    """Delegate to :func:`processor.process_and_assemble_episode` lazily."""

    from .processor import process_and_assemble_episode as _impl

    return _impl(*args, **kwargs)
