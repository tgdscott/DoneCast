"""Deprecated compatibility shim for legacy task imports.

Historically the project exposed Celery tasks directly from ``worker.tasks``
module-level functions.  The refactor to a package-based layout keeps those
implementations in ``worker/tasks/*.py`` modules.  This shim ensures older
imports such as ``from worker.tasks import create_podcast_episode`` continue to
work by re-exporting the symbols from the new package.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

# Allow importing submodules like ``worker.tasks.app`` even though this shim is a
# module.  This mirrors minimal namespace-package behaviour expected by
# ``importlib`` when loading ``worker.tasks.*`` modules.
__path__ = [str(Path(__file__).with_name("tasks"))]

BASE_PACKAGE = "worker.tasks"

_app = import_module(f"{BASE_PACKAGE}.app")
_transcription = import_module(f"{BASE_PACKAGE}.transcription")
_assembly = import_module(f"{BASE_PACKAGE}.assembly")
_publish = import_module(f"{BASE_PACKAGE}.publish")

celery_app = _app.celery_app
transcribe_media_file = _transcription.transcribe_media_file
create_podcast_episode = _assembly.create_podcast_episode
publish_episode_to_spreaker_task = _publish.publish_episode_to_spreaker_task

__all__ = [
    "celery_app",
    "transcribe_media_file",
    "create_podcast_episode",
    "publish_episode_to_spreaker_task",
]
