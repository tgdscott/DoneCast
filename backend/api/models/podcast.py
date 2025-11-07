"""Backward compatibility module - re-exports all models from refactored modules.
This file maintains backward compatibility for existing imports like:
    from api.models.podcast import Episode, Podcast, MediaItem, etc.
All models have been split into separate modules for better organization:
    - enums.py: All enum types
    - podcast_models.py: Podcast-specific models
    - episode.py: Episode-specific models
    - media.py: Media asset models
"""
# Re-export all enums
from .enums import (  # noqa: F401
    MediaCategory,
    EpisodeStatus,
    PodcastType,
    DistributionStatus,
    MusicAssetSource,
    SectionType,
    SectionSourceType,
)
# Re-export all podcast models
from .podcast_models import (  # noqa: F401
    Podcast,
    PodcastBase,
    PodcastImportState,
    PodcastDistributionStatus,
    PodcastTemplate,
    PodcastTemplateCreate,
    PodcastTemplatePublic,
    StaticSegmentSource,
    AIGeneratedSegmentSource,
    TTSSegmentSource,
    TemplateSegment,
)
# Re-export all episode models
from .episode import (  # noqa: F401
    Episode,
    EpisodeSection,
)
# Re-export all media models
from .media import (  # noqa: F401
    MediaItem,
    MusicAsset,
    BackgroundMusicRule,
    SegmentTiming,
)
