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
from api.routers.episodes.common import compute_playback_info, is_published_condition


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
    Fetch ONLY published episodes for a podcast that have audio available.
    Returns recent episodes with audio URLs and metadata.
    Only shows episodes with status == published.
    """
    # Query ONLY published episodes - ORDER BY PUBLISH DATE, NOT CREATION DATE
    from sqlalchemy import case, desc, func
    published_episodes = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(is_published_condition())
        .order_by(
            desc(
                case(
                    (Episode.publish_at != None, Episode.publish_at),  # type: ignore
                    else_=Episode.created_at
                )
            )
        )  # Order by publish_at if available, otherwise created_at - DESCENDING
        .limit(max_count * 2)  # Get more to filter by audio availability (up to 40,000 to ensure we get 20,000 with audio)
    ).all()
    
    episode_data = []
    
    # Process published episodes
    for ep in published_episodes:
        # Get playback URL with OP3 prefix for tracking (public website plays should be tracked)
        playback_info = compute_playback_info(ep, wrap_with_op3=True)
        audio_url = playback_info.get("playback_url")  # Fixed: use playback_url not url
        
        # Skip episodes without valid audio URLs
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
        
        # Use publish_at if available, otherwise fall back to created_at
        # publish_at is the actual publish date, created_at is when episode was assembled
        publish_date = ep.publish_at if ep.publish_at else ep.created_at
        
        episode_data.append(
            PublicEpisodeData(
                id=str(ep.id),
                title=ep.title or "Untitled Episode",
                description=ep.show_notes,
                audio_url=audio_url,
                cover_url=cover_url,
                publish_date=publish_date,
                duration_seconds=None,  # TODO: Calculate from audio file if available
            )
        )
        
        if len(episode_data) >= max_count:
            break
    
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
    
    # Resolve podcast cover URL (same logic as episodes)
    from api.core.logging import get_logger
    log = get_logger(__name__)
    
    podcast_cover_url = None
    log.info(f"[sites] Resolving cover URL for podcast {podcast.id}: cover_path={podcast.cover_path}")
    
    if podcast.cover_path:
        pod_cover_str = str(podcast.cover_path).strip()
        log.info(f"[sites] Cover path string: {pod_cover_str[:100]}...")
        
        if pod_cover_str.lower().startswith(("http://", "https://")):
            # R2 URL - use as-is (or could generate signed URL if needed)
            if ".r2.cloudflarestorage.com" in pod_cover_str.lower():
                podcast_cover_url = pod_cover_str
                log.info(f"[sites] Using R2 URL: {podcast_cover_url[:100]}...")
            elif "spreaker.com" not in pod_cover_str.lower():
                podcast_cover_url = pod_cover_str
                log.info(f"[sites] Using HTTP/HTTPS URL: {podcast_cover_url[:100]}...")
        elif pod_cover_str.startswith("gs://"):
            # GCS path - would need signed URL generation (for now, skip or use compute_cover_info)
            try:
                from api.routers.episodes.common import compute_cover_info
                # Create a dummy episode-like object for compute_cover_info
                class DummyEpisode:
                    cover_path = pod_cover_str
                cover_info = compute_cover_info(DummyEpisode())
                podcast_cover_url = cover_info.get("cover_url")
                log.info(f"[sites] Using GCS resolved URL: {podcast_cover_url[:100] if podcast_cover_url else 'None'}...")
            except Exception as e:
                log.warning(f"[sites] Failed to resolve GCS cover URL: {e}")
        elif pod_cover_str:
            # Local path - serve as static file
            podcast_cover_url = f"/static/media/{os.path.basename(pod_cover_str)}"
            log.info(f"[sites] Using local static path: {podcast_cover_url}")
    else:
        log.warning(f"[sites] Podcast {podcast.id} has no cover_path")
    
    log.info(f"[sites] Final podcast_cover_url: {podcast_cover_url}")
    
    # Fetch published episodes (increased limit to support up to 20,000 episodes)
    episodes = _fetch_published_episodes(session, podcast, max_count=20000)
    
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
        podcast_cover_url=podcast_cover_url,
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
    
    # Resolve podcast cover URL (same logic as main endpoint)
    podcast_cover_url = None
    if podcast.cover_path:
        pod_cover_str = str(podcast.cover_path).strip()
        if pod_cover_str.lower().startswith(("http://", "https://")):
            if ".r2.cloudflarestorage.com" in pod_cover_str.lower():
                podcast_cover_url = pod_cover_str
            elif "spreaker.com" not in pod_cover_str.lower():
                podcast_cover_url = pod_cover_str
        elif pod_cover_str.startswith("gs://"):
            try:
                from api.routers.episodes.common import compute_cover_info
                class DummyEpisode:
                    cover_path = pod_cover_str
                cover_info = compute_cover_info(DummyEpisode())
                podcast_cover_url = cover_info.get("cover_url")
            except Exception:
                pass
        elif pod_cover_str:
            podcast_cover_url = f"/static/media/{os.path.basename(pod_cover_str)}"
    
    # Fetch published episodes (same as public endpoint, increased limit to support up to 20,000 episodes)
    episodes = _fetch_published_episodes(session, podcast, max_count=20000)
    
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
        podcast_cover_url=podcast_cover_url,
        podcast_rss_feed_url=podcast.rss_url,
        sections=section_data_list,
        episodes=episodes,
        global_css=website.global_css,
        status=website.status,
        custom_domain=website.custom_domain,
    )
