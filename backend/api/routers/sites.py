"""
Public website serving endpoint.

Serves podcast websites by subdomain (e.g., cinema-irl.podcastplusplus.com).
No authentication required - public access.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from pydantic import BaseModel, Field

from api.core.database import get_session
from api.models.website import PodcastWebsite
from api.models.website_page import WebsitePage
from api.models.podcast import Podcast, Episode, EpisodeStatus
from api.services.website_sections import get_section_definition
from api.routers.episodes.common import compute_playback_info, is_published_condition

log = logging.getLogger(__name__)

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


class PageData(BaseModel):
    """Page data for navigation."""
    id: str
    title: str
    slug: str
    is_home: bool
    order: int


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
    pages: List[PageData] = Field(default_factory=list)
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
        .where(Episode.episode_number != 0)  # CRITICAL: Exclude placeholder episodes (episode_number=0)
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
    from api.core.logging import get_logger
    log = get_logger(__name__)
    
    try:
        # Look up website by subdomain
        website = session.exec(
            select(PodcastWebsite).where(PodcastWebsite.subdomain == subdomain)
        ).first()
        
        if website is None:
            log.warning(f"[sites] Website not found for subdomain: {subdomain}")
            raise HTTPException(
                status_code=404,
                detail=f"No website found for subdomain: {subdomain}"
            )
        
        # Only show published websites publicly
        if website.status != "published":
            log.info(f"[sites] Website {website.id} status is '{website.status}', not published")
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
        
        # Helper function to resolve R2 URLs to signed URLs
        def resolve_r2_url_to_signed(url_str: str) -> str:
            """Convert R2 URL to signed URL if needed."""
            if not url_str or ".r2.cloudflarestorage.com" not in url_str.lower():
                return url_str
            
            # If already signed (has query params), return as-is
            if "?" in url_str:
                return url_str
            
            # Parse and generate signed URL
            try:
                from urllib.parse import unquote, urlparse
                from infrastructure.r2 import generate_signed_url
                import os
                
                parsed = urlparse(url_str)
                hostname = parsed.hostname or ""
                path = parsed.path
                hostname_parts = hostname.split(".")
                
                if len(hostname_parts) >= 4 and hostname_parts[-3] == "r2":
                    # Format: bucket.account.r2.cloudflarestorage.com/key
                    bucket_name = hostname_parts[0]
                    key = unquote(path.lstrip("/"))
                elif len(hostname_parts) >= 3 and hostname_parts[-2] == "r2":
                    # Format: account.r2.cloudflarestorage.com/bucket/key
                    path_parts = path.lstrip("/").split("/", 1)
                    if len(path_parts) >= 2:
                        bucket_name = path_parts[0]
                        key = unquote(path_parts[1])
                    else:
                        return url_str
                else:
                    return url_str
                
                signed_url = generate_signed_url(bucket_name, key, expiration=86400)
                if signed_url:
                    log.info(f"[sites] Resolved R2 URL to signed URL: {bucket_name}/{key}")
                    return signed_url
            except Exception as e:
                log.warning(f"[sites] Failed to resolve R2 URL: {e}")
            
            return url_str
        
        podcast_cover_url = None
        log.info(f"[sites] Resolving cover URL for podcast {podcast.id}: cover_path={podcast.cover_path}")
        
        if podcast.cover_path:
            pod_cover_str = str(podcast.cover_path).strip()
            log.info(f"[sites] Cover path string: {pod_cover_str[:100]}...")
            
            if pod_cover_str.lower().startswith(("http://", "https://")):
                # R2 URL - resolve to signed URL if needed
                if ".r2.cloudflarestorage.com" in pod_cover_str.lower():
                    podcast_cover_url = resolve_r2_url_to_signed(pod_cover_str)
                    log.info(f"[sites] Using R2 URL (resolved): {podcast_cover_url[:100] if podcast_cover_url else 'None'}...")
                elif "spreaker.com" not in pod_cover_str.lower():
                    podcast_cover_url = pod_cover_str
                    log.info(f"[sites] Using HTTP/HTTPS URL: {podcast_cover_url[:100]}...")
            elif pod_cover_str.startswith("gs://"):
                # GCS path - resolve to signed URL
                try:
                    from api.routers.episodes.common import compute_cover_info
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
        
        # Parse sections data with error handling
        try:
            sections_order = website.get_sections_order()
            sections_config = website.get_sections_config()
            sections_enabled = website.get_sections_enabled()
        except Exception as e:
            log.error(f"[sites] Failed to parse sections data for website {website.id}: {e}", exc_info=True)
            # Fallback to empty sections if parsing fails
            sections_order = []
            sections_config = {}
            sections_enabled = {}
        
        # If no sections configured, use default sections
        if not sections_order:
            log.warning(f"[sites] Website {website.id} has no sections configured, using defaults")
            sections_order = ["header", "hero", "about", "latest-episodes", "subscribe", "footer"]
            # Use default configs if none exist
            if not sections_config:
                sections_config = {}
            if not sections_enabled:
                sections_enabled = {}
        
        # Helper function to resolve logo URLs in section configs
        def resolve_logo_url(logo_url: Optional[str]) -> Optional[str]:
            """Resolve logo URL, preserving R2 signed URLs and generating new ones if needed."""
            if not logo_url:
                return None
            
            logo_url_str = str(logo_url).strip()
            
            # If it's already a signed R2 URL with query params, use as-is
            if ".r2.cloudflarestorage.com" in logo_url_str.lower() and "?" in logo_url_str:
                return logo_url_str
            
            # If it's an R2 URL without query params, generate signed URL
            if ".r2.cloudflarestorage.com" in logo_url_str.lower():
                try:
                    from urllib.parse import unquote, urlparse
                    from infrastructure.r2 import generate_signed_url
                    import os
                    
                    # Parse the URL
                    parsed = urlparse(logo_url_str)
                    hostname = parsed.hostname or ""
                    path = parsed.path
                
                    # Handle R2 URL formats:
                    # 1. bucket.account.r2.cloudflarestorage.com/key (bucket as subdomain - from get_public_url)
                    # 2. account.r2.cloudflarestorage.com/bucket/key (bucket in path - from generate_signed_url)
                    hostname_parts = hostname.split(".")
                    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
                    
                    if len(hostname_parts) >= 4 and hostname_parts[-3] == "r2":
                        # Format 1: bucket.account.r2.cloudflarestorage.com/key
                        # Example: ppp-media.e08eed3e2786f61e25e9e1993c75f61e.r2.cloudflarestorage.com/path/to/file.jpg
                        bucket_name = hostname_parts[0]
                        # Get key from path (remove leading slash)
                        key = unquote(path.lstrip("/"))
                    elif len(hostname_parts) >= 3 and hostname_parts[-2] == "r2" and account_id:
                        # Format 2: account.r2.cloudflarestorage.com/bucket/key
                        # Example: e08eed3e2786f61e25e9e1993c75f61e.r2.cloudflarestorage.com/ppp-media/path/to/file.jpg
                        # Extract bucket from path
                        path_parts = path.lstrip("/").split("/", 1)
                        if len(path_parts) >= 2:
                            bucket_name = path_parts[0]
                            key = unquote(path_parts[1])
                        else:
                            log.warning(f"[sites] Invalid R2 URL format (path-style): {logo_url_str}")
                            return logo_url_str
                    else:
                        log.warning(f"[sites] Could not parse R2 URL: {logo_url_str}")
                        return logo_url_str
                    
                    # Generate signed URL (will return path-style: account.r2.cloudflarestorage.com/bucket/key)
                    signed_url = generate_signed_url(bucket_name, key, expiration=86400)  # 24 hours
                    if signed_url:
                        log.info(f"[sites] Generated signed URL for logo: {bucket_name}/{key}")
                        return signed_url
                    else:
                        log.warning(f"[sites] Failed to generate signed URL for {bucket_name}/{key}")
                except Exception as e:
                    log.warning(f"[sites] Failed to generate signed URL for logo: {e}", exc_info=True)
            
            # If it's a GCS path, resolve it
            if logo_url_str.startswith("gs://"):
                try:
                    from api.routers.episodes.common import compute_cover_info
                    class DummyEpisode:
                        cover_path = logo_url_str
                    cover_info = compute_cover_info(DummyEpisode())
                    resolved_url = cover_info.get("cover_url")
                    if resolved_url:
                        return resolved_url
                except Exception as e:
                    log.warning(f"[sites] Failed to resolve GCS logo URL: {e}")
            
            # Return as-is if no resolution needed
            return logo_url_str
        
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
            
            # Get section config and resolve logo_url if present
            section_config = sections_config.get(section_id, {}).copy()
            if "logo_url" in section_config:
                section_config["logo_url"] = resolve_logo_url(section_config.get("logo_url"))
            
            section_data_list.append(
                SectionData(
                    id=section_def.id,
                    label=section_def.label,
                    category=section_def.category,
                    icon=section_def.icon,
                    description=section_def.description,
                    config=section_config,
                    enabled=True,  # Already filtered for enabled
                )
            )
        
        # Fetch pages for navigation
        pages = session.exec(
            select(WebsitePage)
            .where(WebsitePage.website_id == website.id)
            .order_by(WebsitePage.order, WebsitePage.created_at)
        ).all()
        
        page_data_list = [
            PageData(
                id=str(page.id),
                title=page.title,
                slug=page.slug,
                is_home=page.is_home,
                order=page.order,
            )
            for page in pages
        ]
        
        return PublicWebsiteResponse(
            subdomain=website.subdomain,
            podcast_id=str(website.podcast_id),
            podcast_title=podcast.name,
            podcast_description=podcast.description,
            podcast_cover_url=podcast_cover_url,
            podcast_rss_feed_url=podcast.rss_url,
            sections=section_data_list,
            episodes=episodes,
            pages=page_data_list,
            global_css=website.global_css,
            status=website.status,
            custom_domain=website.custom_domain,
        )
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as e:
        # Log unexpected errors and return 500
        log.error(f"[sites] Unexpected error serving website for subdomain '{subdomain}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load website: {str(e)}"
        )


@router.get("/{subdomain}/preview", response_model=PublicWebsiteResponse)
def preview_website(
    subdomain: str,
    session: Session = Depends(get_session),
):
    """
    Preview website even if not published (for testing).
    
    Same as get_public_website but doesn't check published status.
    Uses the exact same logic to ensure preview matches published site.
    """
    # Reuse the exact same logic as get_public_website
    # Just skip the published status check
    try:
        website = session.exec(
            select(PodcastWebsite).where(PodcastWebsite.subdomain == subdomain)
        ).first()
        
        if website is None:
            raise HTTPException(
                status_code=404,
                detail=f"No website found for subdomain: {subdomain}"
            )
        
        # Skip published status check for preview
        # if website.status != "published":
        #     log.info(f"[sites/preview] Website {website.id} status is '{website.status}' (preview mode allows any status)")
        
        podcast = session.exec(
            select(Podcast).where(Podcast.id == website.podcast_id)
        ).first()
        
        if podcast is None:
            raise HTTPException(status_code=404, detail="Podcast not found")
        
        # Use the EXACT same cover URL resolution logic as get_public_website
        podcast_cover_url = None
        log.info(f"[sites/preview] Resolving cover URL for podcast {podcast.id}: cover_path={podcast.cover_path}")
        
        if podcast.cover_path:
            pod_cover_str = str(podcast.cover_path).strip()
            log.info(f"[sites/preview] Cover path string: {pod_cover_str[:100]}...")
            
            if pod_cover_str.lower().startswith(("http://", "https://")):
                # R2 URL - resolve to signed URL if needed (use same helper function)
                if ".r2.cloudflarestorage.com" in pod_cover_str.lower():
                    # Reuse resolve_r2_url_to_signed logic (defined in get_public_website)
                    try:
                        from urllib.parse import unquote, urlparse
                        from infrastructure.r2 import generate_signed_url
                        
                        # If already signed (has query params), use as-is
                        if "?" in pod_cover_str:
                            podcast_cover_url = pod_cover_str
                        else:
                            # Parse and generate signed URL (same logic as resolve_r2_url_to_signed)
                            parsed = urlparse(pod_cover_str)
                            hostname = parsed.hostname or ""
                            path = parsed.path
                            hostname_parts = hostname.split(".")
                            
                            bucket_name = None
                            key = None
                            
                            if len(hostname_parts) >= 4 and hostname_parts[-3] == "r2":
                                # Format: bucket.account.r2.cloudflarestorage.com/key
                                bucket_name = hostname_parts[0]
                                key = unquote(path.lstrip("/"))
                            elif len(hostname_parts) >= 3 and hostname_parts[-2] == "r2":
                                # Format: account.r2.cloudflarestorage.com/bucket/key
                                path_parts = path.lstrip("/").split("/", 1)
                                if len(path_parts) >= 2:
                                    bucket_name = path_parts[0]
                                    key = unquote(path_parts[1])
                            
                            if bucket_name and key:
                                signed_url = generate_signed_url(bucket_name, key, expiration=86400)
                                if signed_url:
                                    podcast_cover_url = signed_url
                                    log.info(f"[sites/preview] Generated signed URL for cover: {bucket_name}/{key}")
                                else:
                                    podcast_cover_url = pod_cover_str
                            else:
                                podcast_cover_url = pod_cover_str
                    except Exception as e:
                        log.warning(f"[sites/preview] Failed to resolve R2 cover URL: {e}")
                        podcast_cover_url = pod_cover_str
                elif "spreaker.com" not in pod_cover_str.lower():
                    podcast_cover_url = pod_cover_str
                    log.info(f"[sites/preview] Using HTTP/HTTPS URL: {podcast_cover_url[:100]}...")
            elif pod_cover_str.startswith("gs://"):
                # GCS path - resolve to signed URL
                try:
                    from api.routers.episodes.common import compute_cover_info
                    class DummyEpisode:
                        cover_path = pod_cover_str
                    cover_info = compute_cover_info(DummyEpisode())
                    podcast_cover_url = cover_info.get("cover_url")
                    log.info(f"[sites/preview] Using GCS resolved URL: {podcast_cover_url[:100] if podcast_cover_url else 'None'}...")
                except Exception as e:
                    log.warning(f"[sites/preview] Failed to resolve GCS cover URL: {e}")
            elif pod_cover_str:
                # Local path - serve as static file
                podcast_cover_url = f"/static/media/{os.path.basename(pod_cover_str)}"
                log.info(f"[sites/preview] Using local static path: {podcast_cover_url}")
        else:
            log.warning(f"[sites/preview] Podcast {podcast.id} has no cover_path")
        
        log.info(f"[sites/preview] Final podcast_cover_url: {podcast_cover_url}")
        
        # Fetch published episodes (same as public endpoint, increased limit to support up to 20,000 episodes)
        episodes = _fetch_published_episodes(session, podcast, max_count=20000)
        
        # Parse sections data with error handling (same as main endpoint)
        try:
            sections_order = website.get_sections_order()
            sections_config = website.get_sections_config()
            sections_enabled = website.get_sections_enabled()
        except Exception as e:
            log.error(f"[sites/preview] Failed to parse sections data for website {website.id}: {e}", exc_info=True)
            # Fallback to empty sections if parsing fails
            sections_order = []
            sections_config = {}
            sections_enabled = {}
        
        # If no sections configured, use default sections (same as main endpoint)
        if not sections_order:
            log.warning(f"[sites/preview] Website {website.id} has no sections configured, using defaults")
            sections_order = ["header", "hero", "about", "latest-episodes", "subscribe", "footer"]
            if not sections_config:
                sections_config = {}
            if not sections_enabled:
                sections_enabled = {}
        
        # Helper function to resolve logo URLs (same as main endpoint)
        def resolve_logo_url(logo_url: Optional[str]) -> Optional[str]:
            """Resolve logo URL, preserving R2 signed URLs and generating new ones if needed."""
            if not logo_url:
                return None
            
            logo_url_str = str(logo_url).strip()
            
            # If it's already a signed R2 URL with query params, use as-is
            if ".r2.cloudflarestorage.com" in logo_url_str.lower() and "?" in logo_url_str:
                return logo_url_str
            
            # If it's an R2 URL without query params, generate signed URL
            if ".r2.cloudflarestorage.com" in logo_url_str.lower():
                try:
                    from urllib.parse import unquote, urlparse
                    from infrastructure.r2 import generate_signed_url
                    
                    # Parse the URL
                    parsed = urlparse(logo_url_str)
                    hostname = parsed.hostname or ""
                    path = parsed.path
                    
                    # Handle R2 URL formats:
                    # 1. bucket.account.r2.cloudflarestorage.com/key (bucket as subdomain - from get_public_url)
                    # 2. account.r2.cloudflarestorage.com/bucket/key (bucket in path - from generate_signed_url)
                    hostname_parts = hostname.split(".")
                    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
                    
                    if len(hostname_parts) >= 4 and hostname_parts[-3] == "r2":
                        # Format 1: bucket.account.r2.cloudflarestorage.com/key
                        bucket_name = hostname_parts[0]
                        # Get key from path (remove leading slash)
                        key = unquote(path.lstrip("/"))
                    elif len(hostname_parts) >= 3 and hostname_parts[-2] == "r2" and account_id:
                        # Format 2: account.r2.cloudflarestorage.com/bucket/key
                        # Extract bucket from path
                        path_parts = path.lstrip("/").split("/", 1)
                        if len(path_parts) >= 2:
                            bucket_name = path_parts[0]
                            key = unquote(path_parts[1])
                        else:
                            return logo_url_str
                    else:
                        return logo_url_str
                    
                    # Generate signed URL (will return path-style: account.r2.cloudflarestorage.com/bucket/key)
                    signed_url = generate_signed_url(bucket_name, key, expiration=86400)  # 24 hours
                    if signed_url:
                        return signed_url
                except Exception:
                    pass
            
            # If it's a GCS path, resolve it
            if logo_url_str.startswith("gs://"):
                try:
                    from api.routers.episodes.common import compute_cover_info
                    class DummyEpisodePreview:
                        cover_path = logo_url_str
                    cover_info = compute_cover_info(DummyEpisodePreview())
                    resolved_url = cover_info.get("cover_url")
                    if resolved_url:
                        return resolved_url
                except Exception:
                    pass
            
            # Return as-is if no resolution needed
            return logo_url_str
        
        # Build section data array (same as main endpoint)
        section_data_list = []
        for section_id in sections_order:
            # Skip if explicitly disabled
            if not sections_enabled.get(section_id, True):
                continue
            
            # Get section definition
            section_def = get_section_definition(section_id)
            if section_def is None:
                continue  # Skip unknown sections
            
            # Get section config and resolve logo_url if present
            section_config = sections_config.get(section_id, {}).copy()
            if "logo_url" in section_config:
                section_config["logo_url"] = resolve_logo_url(section_config.get("logo_url"))
            
            section_data_list.append(
                SectionData(
                    id=section_def.id,
                    label=section_def.label,
                    category=section_def.category,
                    icon=section_def.icon,
                    description=section_def.description,
                    config=section_config,
                    enabled=True,  # Already filtered for enabled
                )
            )
        
        # Fetch pages for navigation (same as main endpoint)
        pages = session.exec(
            select(WebsitePage)
            .where(WebsitePage.website_id == website.id)
            .order_by(WebsitePage.order, WebsitePage.created_at)
        ).all()
        
        page_data_list = [
            PageData(
                id=str(page.id),
                title=page.title,
                slug=page.slug,
                is_home=page.is_home,
                order=page.order,
            )
            for page in pages
        ]
        
        return PublicWebsiteResponse(
            subdomain=website.subdomain,
            podcast_id=str(website.podcast_id),
            podcast_title=podcast.name,
            podcast_description=podcast.description,
            podcast_cover_url=podcast_cover_url,
            podcast_rss_feed_url=podcast.rss_url,
            sections=section_data_list,
            episodes=episodes,
            pages=page_data_list,
            global_css=website.global_css,
            status=website.status,
            custom_domain=website.custom_domain,
        )
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as e:
        # Log unexpected errors and return 500
        log.error(f"[sites/preview] Unexpected error serving preview for subdomain '{subdomain}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load website preview: {str(e)}"
        )
