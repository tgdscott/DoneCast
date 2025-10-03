"""Celery-free assembly entry point for inline execution."""

from __future__ import annotations

from .orchestrator import orchestrate_create_podcast_episode

__all__ = ["orchestrate_create_podcast_episode"]

