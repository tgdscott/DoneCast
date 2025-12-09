"""Enumeration types used across podcast, episode, and media models.

This module centralizes all enum declarations to avoid duplication and make
it easier to maintain consistent values across the application.
"""
from enum import Enum


class MediaCategory(str, Enum):
    """Categories for media assets (audio files, covers, etc.)."""
    intro = "intro"
    outro = "outro"
    music = "music"
    commercial = "commercial"
    sfx = "sfx"
    main_content = "main_content"
    podcast_cover = "podcast_cover"
    episode_cover = "episode_cover"


class EpisodeStatus(str, Enum):
    """Processing status for episodes."""
    pending = "pending"
    processing = "processing"
    awaiting_audio_decision = "awaiting_audio_decision"
    failed = "failed"
    processed = "processed"
    completed = "completed"
    published = "published"
    error = "error"


class PodcastType(str, Enum):
    """iTunes podcast type classification."""
    episodic = "episodic"
    serial = "serial"


class DistributionStatus(str, Enum):
    """Progress states for 3rd-party distribution destinations."""
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


class MusicAssetSource(str, Enum):
    """Source type for music assets."""
    builtin = "builtin"  # bundled curated loop
    external = "external"  # downloaded from external provider / catalog
    ai = "ai"  # future AI generated asset


class SectionType(str, Enum):
    """Type classification for episode sections."""
    intro = "intro"
    outro = "outro"
    custom = "custom"


class SectionSourceType(str, Enum):
    """Source type for episode sections (TTS, AI-generated, or static audio)."""
    tts = "tts"
    ai_generated = "ai_generated"
    static = "static"
