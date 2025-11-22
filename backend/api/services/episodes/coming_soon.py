"""
Service for creating default "coming soon" trailer episodes for new podcasts.

This allows users to submit their RSS feed to Apple/Spotify immediately
while they prepare their first real episode.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlmodel import Session, select
from sqlalchemy import desc

from ...models.episode import Episode
from ...models.enums import EpisodeStatus
from ...models.podcast import Podcast

logger = logging.getLogger(__name__)

# Reference episode: "The Podcast Plus Plus Podcast" Episode 0 (trailer)
# This episode's audio file is used as the permanent trailer for all new podcasts
REFERENCE_PODCAST_NAME = "The Podcast Plus Plus Podcast"
REFERENCE_EPISODE_NUMBER = 0


def _get_reference_trailer_metadata(session: Session) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Get the audio path, file size, and duration from the reference trailer episode.
    
    Returns:
        Tuple of (audio_path, file_size_bytes, duration_ms) or (None, None, None) if not found
    """
    try:
        from ...models.podcast import Podcast
        
        # Find "The Podcast Plus Plus Podcast" (case-insensitive, flexible matching)
        reference_podcast = session.exec(
            select(Podcast).where(Podcast.name.ilike(f"%{REFERENCE_PODCAST_NAME}%"))
        ).first()
        
        if not reference_podcast:
            logger.warning(
                f"Reference podcast '{REFERENCE_PODCAST_NAME}' not found. "
                "Using fallback defaults for trailer audio."
            )
            return None, None, None
        
        logger.debug(f"Found reference podcast: {reference_podcast.name} (ID: {reference_podcast.id})")
        
        # Find Episode 0 (trailer) for that podcast
        # Try multiple strategies: exact match, then flexible matching
        reference_episode = session.exec(
            select(Episode)
            .where(Episode.podcast_id == reference_podcast.id)
            .where(Episode.episode_number == REFERENCE_EPISODE_NUMBER)
            .where(Episode.episode_type == "trailer")
        ).first()
        
        # If not found with exact match, try without episode_type filter (in case it's not set)
        if not reference_episode:
            logger.debug("Trailer episode not found with exact match, trying without episode_type filter...")
            reference_episode = session.exec(
                select(Episode)
                .where(Episode.podcast_id == reference_podcast.id)
                .where(Episode.episode_number == REFERENCE_EPISODE_NUMBER)
            ).first()
            if reference_episode:
                logger.debug(f"Found Episode 0 without episode_type filter: episode_type={reference_episode.episode_type}")
        
        # If still not found, try finding any trailer episode for this podcast
        if not reference_episode:
            logger.debug("Episode 0 not found, trying to find any trailer episode...")
            all_trailers = session.exec(
                select(Episode)
                .where(Episode.podcast_id == reference_podcast.id)
                .where(Episode.episode_type == "trailer")
                .order_by(Episode.episode_number.asc())
            ).all()
            if all_trailers:
                reference_episode = all_trailers[0]
                logger.debug(f"Found trailer episode: episode_number={reference_episode.episode_number}, id={reference_episode.id}")
        
        # Last resort: find Episode 0 by number only (regardless of type)
        if not reference_episode:
            logger.debug("No trailer found, trying Episode 0 by number only...")
            reference_episode = session.exec(
                select(Episode)
                .where(Episode.podcast_id == reference_podcast.id)
                .where(Episode.episode_number == REFERENCE_EPISODE_NUMBER)
                .order_by(Episode.created_at.desc())
            ).first()
            if reference_episode:
                logger.debug(f"Found Episode 0 by number: episode_type={reference_episode.episode_type}, id={reference_episode.id}")
        
        if not reference_episode:
            logger.warning(
                f"Reference trailer episode (Episode {REFERENCE_EPISODE_NUMBER}) not found for "
                f"'{REFERENCE_PODCAST_NAME}'. Using fallback defaults."
            )
            return None, None, None
        
        audio_path = reference_episode.gcs_audio_path
        file_size = reference_episode.audio_file_size
        duration_ms = reference_episode.duration_ms
        
        if not audio_path:
            logger.warning(
                f"Reference trailer episode has no audio path. Using fallback defaults."
            )
            return None, None, None
        
        logger.info(
            f"✅ Found reference trailer: audio_path={audio_path}, "
            f"size={file_size} bytes, duration={duration_ms} ms"
        )
        
        return audio_path, file_size, duration_ms
        
    except Exception as e:
        logger.warning(
            f"Failed to get reference trailer metadata: {e}. Using fallback defaults.",
            exc_info=True
        )
        return None, None, None


# Fallback defaults (used if reference episode not found)
FALLBACK_AUDIO_PATH = os.getenv(
    "COMING_SOON_AUDIO_PATH",
    "r2://ppp-media/default/coming-soon-trailer.mp3"
)
FALLBACK_AUDIO_FILE_SIZE = int(os.getenv("COMING_SOON_AUDIO_SIZE", "500000"))  # ~500KB default
FALLBACK_AUDIO_DURATION_MS = int(os.getenv("COMING_SOON_AUDIO_DURATION_MS", "30000"))  # 30 seconds default


def create_coming_soon_episode(
    session: Session,
    podcast: Podcast,
    user_id: UUID,
) -> Optional[Episode]:
    """
    Create a default "coming soon" trailer episode for a new podcast.
    
    This episode:
    - Is marked as episode_type="trailer"
    - Is published immediately (status=published)
    - Uses a shared audio file
    - Gets hidden when real episodes are published
    
    Args:
        session: Database session
        podcast: Podcast to create episode for
        user_id: User ID who owns the podcast
        
    Returns:
        Created Episode if successful, None if failed
    """
    try:
        # Check if podcast already has episodes
        existing_episodes = session.exec(
            select(Episode)
            .where(Episode.podcast_id == podcast.id)
            .where(Episode.status == EpisodeStatus.published)
        ).all()
        
        # If there are already published episodes, don't create coming soon episode
        if existing_episodes:
            logger.info(
                f"Podcast {podcast.id} already has {len(existing_episodes)} published episodes, "
                "skipping coming soon episode creation"
            )
            return None
        
        # Check if coming soon episode already exists
        existing_coming_soon = session.exec(
            select(Episode)
            .where(Episode.podcast_id == podcast.id)
            .where(Episode.episode_type == "trailer")
            .where(Episode.title.ilike("%coming soon%"))
        ).first()
        
        if existing_coming_soon:
            logger.info(
                f"Podcast {podcast.id} already has a coming soon episode, skipping creation"
            )
            return existing_coming_soon
        
        # Get audio metadata from reference trailer episode
        audio_path, file_size, duration_ms = _get_reference_trailer_metadata(session)
        
        # Use reference metadata if available, otherwise fall back to defaults
        final_audio_path = audio_path or FALLBACK_AUDIO_PATH
        final_file_size = file_size or FALLBACK_AUDIO_FILE_SIZE
        final_duration_ms = duration_ms or FALLBACK_AUDIO_DURATION_MS
        
        # Create the coming soon episode
        coming_soon_episode = Episode(
            user_id=user_id,
            podcast_id=podcast.id,
            title="Coming Soon - A New Show From Podcast Plus Plus",
            show_notes=(
                "Welcome! This is a placeholder episode. "
                "Your first real episode will replace this one. "
                "Stay tuned for great content coming soon!"
            ),
            episode_type="trailer",
            status=EpisodeStatus.published,
            season_number=1,
            episode_number=0,  # Use 0 to indicate it's a placeholder
            is_explicit=False,
            gcs_audio_path=final_audio_path,
            audio_file_size=final_file_size,
            duration_ms=final_duration_ms,
            publish_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            processed_at=datetime.now(timezone.utc),
        )
        
        session.add(coming_soon_episode)
        session.commit()
        session.refresh(coming_soon_episode)
        
        logger.info(
            f"✅ Created coming soon episode {coming_soon_episode.id} for podcast {podcast.id}"
        )
        
        return coming_soon_episode
        
    except Exception as e:
        logger.error(
            f"❌ Failed to create coming soon episode for podcast {podcast.id}: {e}",
            exc_info=True
        )
        # Don't fail podcast creation if this fails
        return None


def hide_coming_soon_episode_if_needed(
    session: Session,
    podcast_id: UUID,
) -> bool:
    """
    Hide the coming soon episode if the podcast has real published episodes.
    
    This is called when a real episode is published. The coming soon episode
    is set to draft/unpublished status so it doesn't appear in RSS feeds.
    
    Args:
        session: Database session
        podcast_id: Podcast ID to check
        
    Returns:
        True if coming soon episode was hidden, False otherwise
    """
    try:
        # Find coming soon episode
        coming_soon = session.exec(
            select(Episode)
            .where(Episode.podcast_id == podcast_id)
            .where(Episode.episode_type == "trailer")
            .where(Episode.title.ilike("%coming soon%"))
            .where(Episode.status == EpisodeStatus.published)
        ).first()
        
        if not coming_soon:
            return False
        
        # Check if there are real published episodes (excluding the coming soon one)
        real_episodes = session.exec(
            select(Episode)
            .where(Episode.podcast_id == podcast_id)
            .where(Episode.id != coming_soon.id)
            .where(Episode.status == EpisodeStatus.published)
            .where(Episode.episode_type != "trailer")  # Exclude other trailers
        ).all()
        
        if real_episodes:
            # Hide the coming soon episode
            coming_soon.status = EpisodeStatus.processed  # Set to processed (not published)
            session.add(coming_soon)
            session.commit()
            
            logger.info(
                f"✅ Hid coming soon episode {coming_soon.id} for podcast {podcast_id} "
                f"(found {len(real_episodes)} real episodes)"
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(
            f"❌ Failed to hide coming soon episode for podcast {podcast_id}: {e}",
            exc_info=True
        )
        return False

