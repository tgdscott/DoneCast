"""
Public website serving endpoint.

Serves podcast websites by subdomain (e.g., cinema-irl.podcastplusplus.com).
No authentication required - public access.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from pydantic import BaseModel

from api.core.database import get_session
from api.models.website import PodcastWebsite
from api.models.podcast import Podcast, Episode, EpisodeStatus
from api.services.website_sections import get_section_definition
from api.routers.episodes.common import compute_playback_info


router = APIRouter(prefix="/sites", tags=["Public Websites"])


class SectionData(BaseModel):
    """Section data for public rendering."""
    id: str
    label: str
    category: str
    icon: str
    description: str
    config: Dict[str, Any] = {}
    enabled: bool = True


class PublicEpisodeData(BaseModel):
    """Episode data for public website rendering."""
    id: str
    title: str
    description: Optional[str] = None
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None
    publish_date: Optional[datetime] = None
    duration_seconds: Optional[int] = None


class PublicWebsiteResponse(BaseModel):
    """Public website data for rendering."""
    subdomain: str
    podcast_id: str
    podcast_title: str
    podcast_description: Optional[str] = None
    podcast_cover_url: Optional[str] = None
    podcast_rss_feed_url: Optional[str] = None
    sections: List[SectionData]
    episodes: List[PublicEpisodeData]
    global_css: Optional[str] = None
    status: str
    custom_domain: Optional[str] = None


def _fetch_published_episodes(session: Session, podcast: Podcast, max_count: int = 10) -> List[PublicEpisodeData]:
    """
    Fetch published episodes for a podcast.
    Returns recent episodes with audio URLs and metadata.
    """
    # Query published episodes, most recent first
    episodes = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.status == EpisodeStatus.published)
        .order_by(Episode.created_at.desc())  # type: ignore
        .limit(max_count)
    ).all()
    
    episode_data = []
    for ep in episodes:
        # Get playback URL
        playback_info = compute_playback_info(ep)
        audio_url = playback_info.get("url")
        
        # Skip episodes without valid audio URLs (legacy episodes or GCS signing issues)
        if not audio_url:
            continue
        
        # Use compute_cover_info to properly handle gcs_cover_path (R2 URLs)
        from api.routers.episodes.common import compute_cover_info
        cover_info = compute_cover_info(ep)
        cover_url = cover_info.get("cover_url")
        
        # Fallback to podcast cover if episode has no cover
        if not cover_url:
            # For podcast cover, check if it's an R2 URL
            if podcast.cover_path:
                pod_cover_str = str(podcast.cover_path).strip()
                if pod_cover_str.lower().startswith(("http://", "https://")):
                    # Only use if it's not a Spreaker URL and looks like R2
                    if "spreaker.com" not in pod_cover_str.lower() and ".r2.cloudflarestorage.com" in pod_cover_str.lower():
                        cover_url = pod_cover_str
                elif pod_cover_str:
                    # Local path - could be served as static file
                    cover_url = f"/static/media/{os.path.basename(pod_cover_str)}"
        
        episode_data.append(
            PublicEpisodeData(
                id=str(ep.id),
                title=ep.title or "Untitled Episode",
                description=ep.show_notes,
                audio_url=audio_url,
                cover_url=cover_url,
                publish_date=ep.created_at,
                duration_seconds=None,  # TODO: Calculate from audio file if available
            )
        )
    
    return episode_data


@router.get("/{subdomain}", response_model=PublicWebsiteResponse)
def get_public_website(
    subdomain: str,
    session: Session = Depends(get_session),
):
    """
    Get public website data by subdomain.
    
    This endpoint is called when someone visits {subdomain}.podcastplusplus.com
    Returns all section data needed to render the public website.
    """
    # Look up website by subdomain
    website = session.exec(
        select(PodcastWebsite).where(PodcastWebsite.subdomain == subdomain)
    ).first()
    
    if website is None:
        raise HTTPException(
            status_code=404,
            detail=f"No website found for subdomain: {subdomain}"
        )
    
    # Only show published websites publicly
    if website.status != "published":
        raise HTTPException(
            status_code=404,
            detail="Website is not published yet"
        )
    
    # Get podcast details
    podcast = session.exec(
        select(Podcast).where(Podcast.id == website.podcast_id)
    ).first()
    
    if podcast is None:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Fetch published episodes
    episodes = _fetch_published_episodes(session, podcast, max_count=20)
    
    # Parse sections data
    sections_order = website.get_sections_order()
    sections_config = website.get_sections_config()
    sections_enabled = website.get_sections_enabled()
    
    # Build section data array
    section_data_list = []
    for section_id in sections_order:
        # Skip if explicitly disabled
        if not sections_enabled.get(section_id, True):
            continue
        
        # Get section definition
        section_def = get_section_definition(section_id)
        if section_def is None:
            continue  # Skip unknown sections
        
        section_data_list.append(
            SectionData(
                id=section_def.id,
                label=section_def.label,
                category=section_def.category,
                icon=section_def.icon,
                description=section_def.description,
                config=sections_config.get(section_id, {}),
                enabled=True,  # Already filtered for enabled
            )
        )
    
    return PublicWebsiteResponse(
        subdomain=website.subdomain,
        podcast_id=str(website.podcast_id),
        podcast_title=podcast.name,
        podcast_description=podcast.description,
        podcast_cover_url=podcast.cover_path,
        podcast_rss_feed_url=podcast.rss_url,
        sections=section_data_list,
        episodes=episodes,
        global_css=website.global_css,
        status=website.status,
        custom_domain=website.custom_domain,
    )


@router.get("/{subdomain}/preview", response_model=PublicWebsiteResponse)
def preview_website(
    subdomain: str,
    session: Session = Depends(get_session),
):
    """
    Preview website even if not published (for testing).
    
    Same as get_public_website but doesn't check published status.
    Use query param: ?preview=true
    """
    website = session.exec(
        select(PodcastWebsite).where(PodcastWebsite.subdomain == subdomain)
    ).first()
    
    if website is None:
        raise HTTPException(
            status_code=404,
            detail=f"No website found for subdomain: {subdomain}"
        )
    
    podcast = session.exec(
        select(Podcast).where(Podcast.id == website.podcast_id)
    ).first()
    
    if podcast is None:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Fetch published episodes (same as public endpoint)
    episodes = _fetch_published_episodes(session, podcast, max_count=20)
    
    sections_order = website.get_sections_order()
    sections_config = website.get_sections_config()
    sections_enabled = website.get_sections_enabled()
    
    section_data_list = []
    for section_id in sections_order:
        if not sections_enabled.get(section_id, True):
            continue
        
        section_def = get_section_definition(section_id)
        if section_def is None:
            continue
        
        section_data_list.append(
            SectionData(
                id=section_def.id,
                label=section_def.label,
                category=section_def.category,
                icon=section_def.icon,
                description=section_def.description,
                config=sections_config.get(section_id, {}),
                enabled=True,
            )
        )
    
    return PublicWebsiteResponse(
        subdomain=website.subdomain,
        podcast_id=str(website.podcast_id),
        podcast_title=podcast.name,
        podcast_description=podcast.description,
        podcast_cover_url=podcast.cover_path,
        podcast_rss_feed_url=podcast.rss_url,
        sections=section_data_list,
        episodes=episodes,
        global_css=website.global_css,
        status=website.status,
        custom_domain=website.custom_domain,
    )
