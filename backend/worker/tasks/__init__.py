"""Bootstrap for the modular ``worker.tasks`` package.

The legacy monolithic ``worker.tasks`` module exposed a handful of task
functions directly.  This package keeps that import surface stable by
re-exporting the implementations that now live in dedicated modules.  If
something goes wrong when importing the new modules we make a best-effort
attempt to fall back to the legacy ``tasks.py`` implementation so existing
deployments keep working.
"""

from __future__ import annotations

try:
    from .app import celery_app  # backwards-compatible import path
except ModuleNotFoundError:
    celery_app = None  # type: ignore[assignment]
except Exception:
    celery_app = None  # type: ignore[assignment]

# Prefer re-exporting from the new modular implementations
try:  # pragma: no cover - defensive import shim
    from .transcription import transcribe_media_file  # type: ignore F401
except Exception:  # pragma: no cover
    transcribe_media_file = None  # type: ignore[assignment]

try:  # pragma: no cover - defensive import shim
    from .assembly import create_podcast_episode  # type: ignore F401
except Exception:  # pragma: no cover
    create_podcast_episode = None  # type: ignore[assignment]

try:  # pragma: no cover - defensive import shim
    from .publish import publish_episode_to_spreaker_task  # type: ignore F401
except Exception:  # pragma: no cover
    publish_episode_to_spreaker_task = None  # type: ignore[assignment]


def _load_legacy_shim() -> None:
    """Attempt to populate globals from the deprecated ``tasks.py`` module."""

    import importlib.util
    import sys
    from pathlib import Path

    pkg_dir = Path(__file__).resolve().parent
    legacy_mod_path = pkg_dir.parent / "tasks.py"
    if not legacy_mod_path.is_file():
        return

    try:
        spec = importlib.util.spec_from_file_location(
            "worker.tasks_legacy", str(legacy_mod_path)
        )
        if spec and spec.loader:
            legacy = importlib.util.module_from_spec(spec)
            sys.modules["worker.tasks_legacy"] = legacy
            spec.loader.exec_module(legacy)
            for name in (
                "transcribe_media_file",
                "create_podcast_episode",
                "publish_episode_to_spreaker_task",
            ):
                if globals().get(name) is None and hasattr(legacy, name):
                    globals()[name] = getattr(legacy, name)
    except Exception:  # pragma: no cover - fallback is best-effort only
        pass


_required_exports = (
    "transcribe_media_file",
    "create_podcast_episode",
    "publish_episode_to_spreaker_task",
)

# Try to populate from the legacy shim if any expected export is missing.
if not all(globals().get(name) for name in _required_exports):
    _load_legacy_shim()

# Do NOT raise if some exports are still missing. Downstream services already
# handle the absence of specific tasks (e.g., they return 503 or run inline in
# eager mode). Raising here prevents unrelated routers from importing.


__all__ = [
    "celery_app",
    "transcribe_media_file",
    "create_podcast_episode",
    "publish_episode_to_spreaker_task",
]

