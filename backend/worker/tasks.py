"""Compatibility shim for the legacy ``worker.tasks`` module.

The monolithic Celery task implementations now live in the
``worker.tasks`` package (directory).  This module remains so code that
imports ``worker.tasks`` as a module continues to function; we simply
re-export the key objects from their modular homes.  Submodule imports
such as ``worker.tasks.transcription`` keep working because we expose
``__path__`` to point at the package directory.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

__all__ = [
    "celery_app",
    "transcribe_media_file",
    "create_podcast_episode",
    "publish_episode_to_spreaker_task",
]

# Allow ``import worker.tasks.<submodule>`` while this shim is in place.
__path__ = [str(Path(__file__).resolve().parent / "tasks")]  # type: ignore[var-annotated]


def _require(module_name: str, attr_name: str) -> Any:
    """Import ``attr_name`` from ``module_name`` with a helpful error."""

    try:
        module = import_module(module_name)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise ImportError(
            f"worker.tasks shim could not import '{module_name}'. "
            "Ensure the modular task package is available."
        ) from exc
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise ImportError(
            f"worker.tasks shim expected '{attr_name}' in '{module_name}'"
        ) from exc


celery_app = _require("worker.tasks.app", "celery_app")
transcribe_media_file = _require("worker.tasks.transcription", "transcribe_media_file")
create_podcast_episode = _require("worker.tasks.assembly", "create_podcast_episode")
publish_episode_to_spreaker_task = _require("worker.tasks.publish", "publish_episode_to_spreaker_task")
