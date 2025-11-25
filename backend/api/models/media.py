"""Media-related models: MediaItem, MusicAsset, and audio mixing configuration."""
from __future__ import annotations

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.orm import relationship
from typing import List, Optional, Literal, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4
import json
from sqlalchemy.dialects.postgresql import JSON

from .enums import MediaCategory, MusicAssetSource
from .user import User

if TYPE_CHECKING:
    pass


class BackgroundMusicRule(SQLModel):
    """Configuration for background music ducking and mixing."""
    id: UUID = Field(default_factory=uuid4)
    music_filename: Optional[str] = None  # Deprecated: use music_asset_id instead
    music_asset_id: Optional[str] = None  # New: reference to MusicAsset by ID
    apply_to_segments: List[Literal["intro", "content", "outro"]]
    start_offset_s: float = 0.0
    end_offset_s: float = 0.0
    fade_in_s: float = 2.0
    fade_out_s: float = 3.0
    volume_db: float = -15.0


class SegmentTiming(SQLModel):
    """Timing offsets for episode segment assembly."""
    # Defaults are zero (no overlap). Users can specify negative values to overlap.
    content_start_offset_s: float = 0.0
    outro_start_offset_s: float = 0.0


class MediaItem(SQLModel, table=True):
    """User-uploaded media files (audio, covers, etc.) with transcription tracking."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    friendly_name: Optional[str] = Field(default=None)
    category: MediaCategory = Field(default=MediaCategory.music)
    filename: str
    content_type: Optional[str] = None
    filesize: Optional[int] = None
    # Optional spoken trigger keyword (used for SFX insertion during cleanup if spoken in content)
    trigger_keyword: Optional[str] = Field(default=None, index=False, description="Spoken keyword that triggers this media as SFX")
    user_id: UUID = Field(foreign_key="user.id")
    user: Optional[User] = Relationship(sa_relationship=relationship("User"))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # When to expire this raw upload (UTC). For main_content, defaults to the first 2am PT boundary after upload + 14 days.
    expires_at: Optional[datetime] = Field(default=None, description="UTC timestamp when this media item should be purged if unused")
    # Track which episode consumed this raw file (for 'safe to delete' notifications when auto-delete is disabled)
    used_in_episode_id: Optional[UUID] = Field(default=None, foreign_key="episode.id", description="Episode that used this raw file during assembly")
    
    # Transcription status - True when transcript is available and file is ready for assembly
    transcript_ready: bool = Field(default=False, description="True when transcription is complete and file is ready for episode assembly")
    transcription_error: Optional[str] = Field(default=None, description="Error message if transcription failed or detected instrumental/silence")
    
    # CRITICAL: Sole source of truth for transcription routing
    # Set when file is uploaded based on checkbox. Determines Auphonic vs AssemblyAI.
    use_auphonic: bool = Field(default=False, description="True if Auphonic transcription was requested (set by upload checkbox)")
    
    # Auphonic integration fields
    auphonic_processed: bool = Field(default=False, description="True if Auphonic processed this file")
    auphonic_cleaned_audio_url: Optional[str] = Field(default=None, description="GCS URL of Auphonic's cleaned/processed audio")
    auphonic_original_audio_url: Optional[str] = Field(default=None, description="GCS URL of original audio (kept for failure diagnosis)")
    auphonic_output_file: Optional[str] = Field(default=None, description="GCS URL of single Auphonic output file")
    auphonic_metadata: Optional[str] = Field(default=None, description="JSON string with show_notes, chapters (if returned separately)")

    # Speaker identification guests
    guest_ids: Optional[list] = Field(default=None, sa_column=Column(JSON), description="List of guest_library IDs associated with this upload for transcription")



class MusicAsset(SQLModel, table=True):
    """Curated or user-uploaded music loops for background audio."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    display_name: str
    filename: str
    duration_s: Optional[float] = None
    mood_tags_json: str = Field(default="[]")  # JSON list of strings
    source_type: MusicAssetSource = Field(default=MusicAssetSource.builtin)
    license: Optional[str] = None
    attribution: Optional[str] = None
    user_select_count: int = Field(default=0, description="How many times users picked this asset")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Global vs user-owned music
    is_global: bool = Field(default=False, description="True if this is a globally accessible music asset (admin-uploaded)")
    owner_id: Optional[UUID] = Field(default=None, foreign_key="user.id", index=True, description="User who owns this asset; None for global/admin assets")

    def mood_tags(self) -> List[str]:
        """Parse mood tags from JSON string."""
        try:
            return json.loads(self.mood_tags_json)
        except Exception:
            return []


_ns = globals().copy()
_ns.update({'User': User})
BackgroundMusicRule.model_rebuild(_types_namespace=_ns)
SegmentTiming.model_rebuild(_types_namespace=_ns)
MediaItem.model_rebuild(_types_namespace=_ns)
MusicAsset.model_rebuild(_types_namespace=_ns)
