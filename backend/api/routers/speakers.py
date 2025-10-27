"""
Speaker Configuration API Endpoints

Manages host speaker intros (podcast-level) and guest speaker intros (episode-level).

Routes:
- POST /api/podcasts/{podcast_id}/speakers - Configure podcast speakers
- GET /api/podcasts/{podcast_id}/speakers - List configured speakers
- POST /api/podcasts/{podcast_id}/speakers/{speaker_name}/intro - Upload voice intro
- DELETE /api/podcasts/{podcast_id}/speakers/{speaker_name} - Remove speaker
- POST /api/episodes/{episode_id}/guests - Configure episode guests
- GET /api/episodes/{episode_id}/guests - List episode guests
- POST /api/episodes/{episode_id}/guests/{guest_name}/intro - Upload guest voice intro
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from pydantic import BaseModel
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Episode, Podcast
from api.models.user import User
from api.routers.auth.utils import get_current_user
from infrastructure import gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["speakers"])


# ========== REQUEST/RESPONSE MODELS ==========

class SpeakerConfig(BaseModel):
    """Single speaker configuration."""
    name: str
    gcs_path: Optional[str] = None  # GCS URL of voice intro audio
    order: int  # Speaking order (0-indexed)


class PodcastSpeakersConfig(BaseModel):
    """Podcast-level speaker configuration."""
    has_guests: bool = False
    hosts: List[SpeakerConfig]


class GuestConfig(BaseModel):
    """Episode-level guest configuration."""
    name: str
    gcs_path: Optional[str] = None


class EpisodeGuestsConfig(BaseModel):
    """Episode-level guest configuration."""
    guests: List[GuestConfig]


# ========== PODCAST SPEAKER ENDPOINTS ==========

@router.get("/podcasts/{podcast_id}/speakers")
async def get_podcast_speakers(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PodcastSpeakersConfig:
    """Get podcast speaker configuration."""
    
    podcast = session.exec(
        select(Podcast).where(Podcast.id == podcast_id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Check ownership
    if podcast.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your podcast")
    
    # Parse speaker_intros JSON
    speaker_intros = podcast.speaker_intros or {}
    hosts_data = speaker_intros.get("hosts", [])
    
    hosts = [
        SpeakerConfig(
            name=host.get("name", ""),
            gcs_path=host.get("gcs_path"),
            order=idx
        )
        for idx, host in enumerate(hosts_data)
    ]
    
    return PodcastSpeakersConfig(
        has_guests=podcast.has_guests or False,
        hosts=hosts
    )


@router.post("/podcasts/{podcast_id}/speakers")
async def update_podcast_speakers(
    podcast_id: UUID,
    config: PodcastSpeakersConfig,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update podcast speaker configuration (hosts + guest flag)."""
    
    podcast = session.exec(
        select(Podcast).where(Podcast.id == podcast_id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    if podcast.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your podcast")
    
    # Build speaker_intros JSON
    hosts_data = [
        {
            "name": host.name,
            "gcs_path": host.gcs_path,
            "order": host.order
        }
        for host in sorted(config.hosts, key=lambda h: h.order)
    ]
    
    speaker_intros = {"hosts": hosts_data}
    
    # Update podcast
    podcast.speaker_intros = speaker_intros
    podcast.has_guests = config.has_guests
    
    session.add(podcast)
    session.commit()
    
    logger.info(
        "[speakers] Updated podcast %s: %d hosts, has_guests=%s",
        podcast_id,
        len(hosts_data),
        config.has_guests
    )
    
    return {"ok": True, "hosts_count": len(hosts_data)}


@router.post("/podcasts/{podcast_id}/speakers/{speaker_name}/intro")
async def upload_speaker_intro(
    podcast_id: UUID,
    speaker_name: str,
    intro_audio: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload voice intro for a podcast speaker (host)."""
    
    podcast = session.exec(
        select(Podcast).where(Podcast.id == podcast_id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    if podcast.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your podcast")
    
    # Validate file type
    content_type = intro_audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Expected audio file."
        )
    
    # Read file content
    audio_bytes = await intro_audio.read()
    
    if len(audio_bytes) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(
            status_code=400,
            detail="Voice intro too large (max 5MB, ~30 seconds recommended)"
        )
    
    # Upload to GCS
    from api.core.config import settings
    
    # Sanitize speaker name for filename
    safe_name = "".join(c if c.isalnum() else "_" for c in speaker_name.lower())
    filename = f"speaker_intros/{podcast_id}/{safe_name}_intro.wav"
    
    try:
        gcs_uri = gcs.upload_bytes(
            settings.GCS_BUCKET,
            filename,
            audio_bytes,
            content_type=content_type
        )
        
        logger.info(
            "[speakers] Uploaded intro for %s (podcast %s): %s",
            speaker_name,
            podcast_id,
            gcs_uri
        )
        
    except Exception as e:
        logger.error("[speakers] Failed to upload intro to GCS: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to upload voice intro to cloud storage"
        )
    
    # Update speaker_intros JSON
    speaker_intros = podcast.speaker_intros or {"hosts": []}
    hosts = speaker_intros.get("hosts", [])
    
    # Find speaker and update gcs_path
    updated = False
    for host in hosts:
        if host.get("name") == speaker_name:
            host["gcs_path"] = gcs_uri
            updated = True
            break
    
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Speaker '{speaker_name}' not found in podcast configuration"
        )
    
    speaker_intros["hosts"] = hosts
    podcast.speaker_intros = speaker_intros
    
    session.add(podcast)
    session.commit()
    
    return {
        "ok": True,
        "speaker": speaker_name,
        "gcs_uri": gcs_uri,
        "size_bytes": len(audio_bytes)
    }


@router.delete("/podcasts/{podcast_id}/speakers/{speaker_name}")
async def delete_speaker(
    podcast_id: UUID,
    speaker_name: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a speaker from podcast configuration."""
    
    podcast = session.exec(
        select(Podcast).where(Podcast.id == podcast_id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    if podcast.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your podcast")
    
    speaker_intros = podcast.speaker_intros or {"hosts": []}
    hosts = speaker_intros.get("hosts", [])
    
    # Remove speaker
    original_count = len(hosts)
    hosts = [h for h in hosts if h.get("name") != speaker_name]
    
    if len(hosts) == original_count:
        raise HTTPException(
            status_code=404,
            detail=f"Speaker '{speaker_name}' not found"
        )
    
    speaker_intros["hosts"] = hosts
    podcast.speaker_intros = speaker_intros
    
    session.add(podcast)
    session.commit()
    
    logger.info("[speakers] Removed speaker %s from podcast %s", speaker_name, podcast_id)
    
    return {"ok": True, "removed": speaker_name}


# ========== EPISODE GUEST ENDPOINTS ==========

@router.get("/episodes/{episode_id}/guests")
async def get_episode_guests(
    episode_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> EpisodeGuestsConfig:
    """Get episode guest configuration."""
    
    episode = session.exec(
        select(Episode).where(Episode.id == episode_id)
    ).first()
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your episode")
    
    guest_intros = episode.guest_intros or []
    
    guests = [
        GuestConfig(
            name=guest.get("name", ""),
            gcs_path=guest.get("gcs_path")
        )
        for guest in guest_intros
    ]
    
    return EpisodeGuestsConfig(guests=guests)


@router.post("/episodes/{episode_id}/guests")
async def update_episode_guests(
    episode_id: UUID,
    config: EpisodeGuestsConfig,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update episode guest configuration."""
    
    episode = session.exec(
        select(Episode).where(Episode.id == episode_id)
    ).first()
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your episode")
    
    # Build guest_intros JSON
    guests_data = [
        {
            "name": guest.name,
            "gcs_path": guest.gcs_path
        }
        for guest in config.guests
    ]
    
    episode.guest_intros = guests_data
    
    session.add(episode)
    session.commit()
    
    logger.info("[speakers] Updated episode %s: %d guests", episode_id, len(guests_data))
    
    return {"ok": True, "guests_count": len(guests_data)}


@router.post("/episodes/{episode_id}/guests/{guest_name}/intro")
async def upload_guest_intro(
    episode_id: UUID,
    guest_name: str,
    intro_audio: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload voice intro for an episode guest."""
    
    episode = session.exec(
        select(Episode).where(Episode.id == episode_id)
    ).first()
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your episode")
    
    # Validate file type
    content_type = intro_audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Expected audio file."
        )
    
    # Read file content
    audio_bytes = await intro_audio.read()
    
    if len(audio_bytes) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(
            status_code=400,
            detail="Voice intro too large (max 5MB, ~30 seconds recommended)"
        )
    
    # Upload to GCS
    from api.core.config import settings
    
    safe_name = "".join(c if c.isalnum() else "_" for c in guest_name.lower())
    filename = f"guest_intros/{episode_id}/{safe_name}_intro.wav"
    
    try:
        gcs_uri = gcs.upload_bytes(
            settings.GCS_BUCKET,
            filename,
            audio_bytes,
            content_type=content_type
        )
        
        logger.info(
            "[speakers] Uploaded guest intro for %s (episode %s): %s",
            guest_name,
            episode_id,
            gcs_uri
        )
        
    except Exception as e:
        logger.error("[speakers] Failed to upload guest intro to GCS: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to upload voice intro to cloud storage"
        )
    
    # Update guest_intros JSON
    guest_intros = episode.guest_intros or []
    
    # Find guest and update gcs_path
    updated = False
    for guest in guest_intros:
        if guest.get("name") == guest_name:
            guest["gcs_path"] = gcs_uri
            updated = True
            break
    
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Guest '{guest_name}' not found in episode configuration"
        )
    
    episode.guest_intros = guest_intros
    
    session.add(episode)
    session.commit()
    
    return {
        "ok": True,
        "guest": guest_name,
        "gcs_uri": gcs_uri,
        "size_bytes": len(audio_bytes)
    }
