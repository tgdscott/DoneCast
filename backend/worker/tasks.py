"""Compatibility layer for legacy task imports.

This module re-exports task callables from the package structure introduced
in 2024. The real implementations live inside ``worker.tasks.*`` modules.
"""

from worker.tasks.app import celery_app  # noqa: F401
from worker.tasks.assembly import create_podcast_episode  # noqa: F401
from worker.tasks.publishing import publish_episode_to_spreaker_task  # noqa: F401
from worker.tasks.transcription import transcribe_media_file  # noqa: F401

__all__ = [
    "celery_app",
    "create_podcast_episode",
    "publish_episode_to_spreaker_task",
    "transcribe_media_file",
]

