"""Episode-related models: Episode and EpisodeSection."""
from __future__ import annotations

from sqlmodel import SQLModel, Field, Column, Relationship
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy.dialects.postgresql import JSON
import json

from .enums import EpisodeStatus, SectionType, SectionSourceType

if TYPE_CHECKING:
    from .user import User
    from .podcast_models import Podcast, PodcastTemplate


class Episode(SQLModel, table=True):
    """Podcast episode with metadata, status tracking, and audio processing fields."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    
    user_id: UUID = Field(foreign_key="user.id")
    user: Optional["User"] = Relationship()
    template_id: Optional[UUID] = Field(default=None, foreign_key="podcasttemplate.id")
    template: Optional["PodcastTemplate"] = Relationship(back_populates="episodes")
    podcast_id: UUID = Field(foreign_key="podcast.id")
    podcast: Optional["Podcast"] = Relationship(back_populates="episodes")

    title: str = Field(default="Untitled Episode")
    cover_path: Optional[str] = Field(default=None)
    show_notes: Optional[str] = Field(default=None)
    season_number: Optional[int] = Field(default=None, description="Season number for ordering/auto-increment")
    episode_number: Optional[int] = Field(default=None, description="Episode number within the season")
    # Extended editable metadata (locally stored; some not yet propagated to Spreaker API)
    tags_json: Optional[str] = Field(default="[]", description="JSON list of tag strings (AI generated soon)")
    is_explicit: bool = Field(default=False, description="Explicit content flag (local; mirror to Spreaker when API exposed)")
    episode_type: Optional[str] = Field(default="full", description="iTunes episode type: full, trailer, or bonus")
    image_crop: Optional[str] = Field(default=None, description="Crop rectangle 'x1,y1,x2,y2' for square extraction when pushing to Spreaker")
    
    status: EpisodeStatus = Field(default=EpisodeStatus.pending)
    final_audio_path: Optional[str] = Field(default=None)
    spreaker_episode_id: Optional[str] = Field(default=None)
    is_published_to_spreaker: bool = Field(default=False)
    remote_cover_url: Optional[str] = Field(default=None, description="Spreaker-hosted cover image URL after publish")
    # GCS retention for 7-day grace period (kept after assembly/schedule until 7 days post-publish)
    gcs_audio_path: Optional[str] = Field(default=None, description="GCS path (gs://...) for assembled audio during retention period")
    gcs_cover_path: Optional[str] = Field(default=None, description="GCS path (gs://...) for episode cover during retention period")
    # Numbering conflict flag (soft warning, doesn't block assembly/update)
    has_numbering_conflict: bool = Field(default=False, description="True if season+episode number duplicates exist in this podcast")
    # Publish failure diagnostics
    spreaker_publish_error: Optional[str] = Field(default=None, description="Short error label from last Spreaker publish attempt")
    spreaker_publish_error_detail: Optional[str] = Field(default=None, description="Detailed error payload / message from last attempt")
    needs_republish: bool = Field(default=False, description="Set true when assembly succeeded but publish failed; UI can offer retry without reassembly")
    # Audio pipeline metadata & working filename for in-progress/cleaned content
    meta_json: Optional[str] = Field(default="{}", description="Arbitrary JSON metadata for processing (flubber contexts, cuts, etc.)")
    working_audio_name: Optional[str] = Field(default=None, description="Current working audio basename (e.g., cleaned content) used as source for final mixing")
    
    # Auphonic integration (Professional Audio Processing for Creator+ tiers)
    auphonic_production_id: Optional[str] = Field(default=None, description="Auphonic production UUID for this episode (if processed with Auphonic)")
    auphonic_processed: bool = Field(default=False, description="True if this episode was processed with Auphonic's professional audio engine")
    auphonic_error: Optional[str] = Field(default=None, description="Error message from Auphonic processing (if failed)")
    
    # Auphonic metadata (from Whisper ASR + AI processing)
    brief_summary: Optional[str] = Field(default=None, description="Brief 1-2 paragraph AI-generated summary (for show notes)")
    long_summary: Optional[str] = Field(default=None, description="Detailed multi-paragraph AI-generated summary (for marketing/blog posts)")
    episode_tags: Optional[str] = Field(default="[]", description="JSON array of AI-extracted tags/keywords (for SEO)")
    episode_chapters: Optional[str] = Field(default="[]", description="JSON array of chapter markers with titles and timestamps (for podcast apps)")
    
    # Self-hosted RSS feed requirements
    audio_file_size: Optional[int] = Field(default=None, description="Audio file size in bytes (required for RSS <enclosure> length attribute)")
    duration_ms: Optional[int] = Field(default=None, description="Episode duration in milliseconds (for iTunes <duration> tag)")
    
    # Speaker identification (per-episode guests)
    guest_intros: Optional[list] = Field(default=None, sa_column=Column(JSON), description="Per-episode guest voice intros for speaker identification - format: [{'name': 'Sarah', 'gcs_path': 'gs://...', 'duration_ms': 2000}]")

    processed_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp (added via migration)")
    publish_at: Optional[datetime] = Field(default=None)
    # Raw local-time string as originally entered by the user (no timezone math),
    # so UI can display exactly what they chose even though publish_at is stored UTC.
    publish_at_local: Optional[str] = Field(default=None)
    
    # Source provenance fields (from original feed)
    original_guid: Optional[str] = Field(default=None, index=True, description="Original RSS item GUID")
    source_media_url: Optional[str] = Field(default=None, description="Original enclosure URL")
    source_published_at: Optional[datetime] = Field(default=None, description="Original published datetime from feed")
    source_checksum: Optional[str] = Field(default=None, description="Optional checksum of source media")

    # Compatibility: legacy .description maps to .show_notes
    @property
    def description(self):
        """Backward compatibility property for .description → .show_notes."""
        return getattr(self, 'show_notes', None)

    def tags(self) -> List[str]:
        """Parse and return list of tags from JSON string."""
        try:
            return json.loads(self.tags_json or "[]")
        except Exception:
            return []

    def set_tags(self, tags: List[str]):
        """Set tags from a list, serializing to JSON."""
        try:
            self.tags_json = json.dumps([t for t in tags if t])
        except Exception:
            self.tags_json = json.dumps([])


class EpisodeSection(SQLModel, table=True):
    """A short, tagged section script/prompt used for intros/outros/etc.

    Notes:
    - tag: logical name/category (e.g., "Interview Intro", "Short Outro").
        We cap distinct tags per podcast via router logic.
    - section_type: intro/outro/custom for filtering/history.
    - content: the script text (for TTS) or prompt text (for AI-generated).
    - episode_id is optional to allow saving drafts before episode creation.
    - voice metadata persists the chosen TTS voice for future reuse.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id")
    user: Optional["User"] = Relationship()
    podcast_id: UUID = Field(foreign_key="podcast.id")
    podcast: Optional["Podcast"] = Relationship()
    episode_id: Optional[UUID] = Field(default=None, foreign_key="episode.id")
    episode: Optional["Episode"] = Relationship()

    tag: str = Field(index=True)
    section_type: SectionType = Field(default=SectionType.intro)
    source_type: SectionSourceType = Field(default=SectionSourceType.tts)
    content: str = Field(default="")
    voice_id: Optional[str] = Field(default=None)
    voice_name: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
