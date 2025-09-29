"""Audio task compatibility layer."""

from __future__ import annotations

from .assembly import create_podcast_episode  # re-export for legacy imports
from .manual_cut import manual_cut_episode  # re-export for legacy imports

__all__ = [
    "create_podcast_episode",
    "manual_cut_episode",
]

