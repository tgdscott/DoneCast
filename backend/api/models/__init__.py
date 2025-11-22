"""Aggregate exports for model convenience imports.

Prefer importing specific models from their modules, but keep these for backwards compatibility.
"""

# Enum exports
from .enums import (  # noqa: F401
    MediaCategory,
    EpisodeStatus,
    PodcastType,
    DistributionStatus,
    MusicAssetSource,
    SectionType,
    SectionSourceType,
)

# Podcast models
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

# Episode models
from .episode import (  # noqa: F401
    Episode,
    EpisodeSection,
)

# Media models
from .media import (  # noqa: F401
    MediaItem,
    MusicAsset,
    BackgroundMusicRule,
    SegmentTiming,
)

# User models
from .user import User, UserCreate, UserPublic, UserTermsAcceptance  # noqa: F401

# Promo code models
from .promo_code import PromoCode, PromoCodeCreate, PromoCodeUpdate, PromoCodePublic  # noqa: F401

# Affiliate code models
from .affiliate_code import UserAffiliateCode, UserAffiliateCodePublic  # noqa: F401

# Other models
from .subscription import Subscription  # noqa: F401
from .settings import AppSetting  # noqa: F401
from .usage import ProcessingMinutesLedger, LedgerDirection, LedgerReason  # noqa: F401
from .recurring import RecurringSchedule  # noqa: F401
from .website import PodcastWebsite, PodcastWebsiteStatus  # noqa: F401
from .website_page import WebsitePage  # noqa: F401
from .transcription import TranscriptionWatch  # noqa: F401
from .admin_log import AdminActionLog, AdminActionType  # noqa: F401
