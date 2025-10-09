"""
Self-hosted RSS 2.0 podcast feed generation.

This replaces Spreaker's RSS feed with our own, giving full control over:
- Episode delivery (from GCS with signed URLs or public CDN)
- Feed metadata and iTunes tags
- Analytics and tracking
- No platform fees or restrictions
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional
from uuid import UUID
import xml.etree.ElementTree as ET
from xml.dom import minidom

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select, desc

from api.core.database import get_session
from api.models.podcast import Podcast, Episode, EpisodeStatus
from api.core.config import settings
from infrastructure.gcs import get_public_audio_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rss", tags=["rss-feed"])


def _format_rfc2822(dt: Optional[datetime]) -> str:
    """Format datetime as RFC 2822 (required for RSS pubDate)"""
    if not dt:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def _format_duration(duration_ms: Optional[int]) -> str:
    """Format duration in HH:MM:SS or MM:SS"""
    if not duration_ms:
        return "00:00"
    total_seconds = duration_ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"





def _generate_podcast_rss(podcast: Podcast, episodes: List[Episode], base_url: str) -> str:
    """Generate RSS 2.0 feed XML for a podcast with iTunes namespace tags."""
    
    # Root RSS element with namespaces
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:podcast": "https://podcastindex.org/namespace/1.0",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
    })
    
    channel = ET.SubElement(rss, "channel")
    
    # Required channel elements
    ET.SubElement(channel, "title").text = podcast.name
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = podcast.description or "A podcast"
    ET.SubElement(channel, "language").text = podcast.language or "en"
    
    # iTunes tags
    ET.SubElement(channel, "itunes:author").text = podcast.author_name or podcast.owner_name or "Unknown"
    ET.SubElement(channel, "itunes:explicit").text = "no"  # TODO: Make configurable
    
    # Podcast owner (required for iTunes submission)
    if podcast.contact_email or podcast.owner_name:
        owner = ET.SubElement(channel, "itunes:owner")
        if podcast.owner_name:
            ET.SubElement(owner, "itunes:name").text = podcast.owner_name
        if podcast.contact_email:
            ET.SubElement(owner, "itunes:email").text = podcast.contact_email
    
    # Podcast image
    cover_url = None
    if podcast.remote_cover_url:
        cover_url = podcast.remote_cover_url
    elif podcast.cover_path and podcast.cover_path.startswith("http"):
        cover_url = podcast.cover_path
    
    if cover_url:
        ET.SubElement(channel, "itunes:image", {"href": cover_url})
        image_elem = ET.SubElement(channel, "image")
        ET.SubElement(image_elem, "url").text = cover_url
        ET.SubElement(image_elem, "title").text = podcast.name
        ET.SubElement(image_elem, "link").text = base_url
    
    # Podcast categories (iTunes)
    # TODO: Map category_id to iTunes category names
    ET.SubElement(channel, "itunes:category", {"text": "Technology"})
    
    # Copyright
    if podcast.copyright_line:
        ET.SubElement(channel, "copyright").text = podcast.copyright_line
    
    # Podcast GUID (for ownership verification)
    if podcast.podcast_guid:
        ET.SubElement(channel, "podcast:guid").text = podcast.podcast_guid
    
    # Last build date
    ET.SubElement(channel, "lastBuildDate").text = _format_rfc2822(datetime.now(timezone.utc))
    
    # Generate episode items (most recent first)
    for episode in episodes:
        item = ET.SubElement(channel, "item")
        
        ET.SubElement(item, "title").text = episode.title
        ET.SubElement(item, "itunes:title").text = episode.title
        
        # Description / show notes
        description = episode.show_notes or episode.title
        ET.SubElement(item, "description").text = description
        ET.SubElement(item, "itunes:summary").text = description[:4000]  # iTunes limit
        
        # GUID (unique identifier for this episode)
        guid_text = episode.original_guid or str(episode.id)
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = guid_text
        
        # Publication date
        pub_date = episode.publish_at or episode.source_published_at or episode.processed_at
        ET.SubElement(item, "pubDate").text = _format_rfc2822(pub_date)
        
        # Episode audio enclosure
        audio_url = None
        if episode.gcs_audio_path:
            logger.info(f"RSS Feed: Generating audio URL for episode {episode.episode_number}: {episode.gcs_audio_path}")
            audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
            if audio_url:
                logger.info(f"RSS Feed: Generated audio URL for episode {episode.episode_number}")
            else:
                logger.warning(f"RSS Feed: Failed to generate audio URL for episode {episode.episode_number}")
        else:
            logger.warning(f"RSS Feed: Episode {episode.episode_number} has no gcs_audio_path")
        
        if audio_url:
            # Get file size (required for RSS enclosure)
            file_size = getattr(episode, "audio_file_size", None) or 0
            ET.SubElement(item, "enclosure", {
                "url": audio_url,
                "type": "audio/mpeg",
                "length": str(file_size),
            })
        
        # Episode image
        episode_image = None
        if episode.remote_cover_url:
            episode_image = episode.remote_cover_url
        elif episode.gcs_cover_path:
            episode_image = get_public_audio_url(episode.gcs_cover_path, expiration_days=7)
        elif episode.cover_path and episode.cover_path.startswith("http"):
            episode_image = episode.cover_path
        
        if episode_image:
            ET.SubElement(item, "itunes:image", {"href": episode_image})
        
        # Duration (if available)
        duration_ms = getattr(episode, "duration_ms", None)
        if duration_ms:
            ET.SubElement(item, "itunes:duration").text = _format_duration(duration_ms)
        
        # Episode number and season
        if episode.episode_number:
            ET.SubElement(item, "itunes:episode").text = str(episode.episode_number)
        if episode.season_number:
            ET.SubElement(item, "itunes:season").text = str(episode.season_number)
        
        # Explicit flag
        ET.SubElement(item, "itunes:explicit").text = "yes" if episode.is_explicit else "no"
        
        # Episode type (full, trailer, bonus)
        ET.SubElement(item, "itunes:episodeType").text = "full"  # TODO: Make configurable
        
        # Tags as keywords
        tags = episode.tags()
        if tags:
            ET.SubElement(item, "itunes:keywords").text = ", ".join(tags[:10])
    
    # Pretty print XML
    xml_string = ET.tostring(rss, encoding="unicode")
    dom = minidom.parseString(xml_string)
    return dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


@router.get("/{podcast_identifier}/feed.xml", response_class=Response)
def get_podcast_feed(
    podcast_identifier: str,
    session: Session = Depends(get_session),
):
    """
    Generate RSS 2.0 podcast feed for a specific podcast.
    
    Supports both friendly slugs and UUIDs:
    - https://yoursite.com/rss/my-awesome-podcast/feed.xml (friendly!)
    - https://yoursite.com/rss/{uuid}/feed.xml (still works)
    
    This feed can be submitted to Apple Podcasts, Spotify, Google Podcasts, etc.
    """
    
    # Try to find podcast by slug first (friendly URL)
    podcast = session.exec(
        select(Podcast).where(Podcast.slug == podcast_identifier)
    ).first()
    
    # If not found by slug, try UUID
    if not podcast:
        try:
            podcast_uuid = UUID(podcast_identifier)
            podcast = session.get(Podcast, podcast_uuid)
        except (ValueError, AttributeError):
            pass
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Get all published episodes, ordered by publish date (newest first)
    statement = (
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.status == EpisodeStatus.published)
        .order_by(desc(Episode.publish_at))
    )
    episodes = session.exec(statement).all()
    
    # Generate feed XML - use slug if available, otherwise ID
    podcast_path = podcast.slug or str(podcast.id)
    frontend_domain = getattr(settings, "APP_BASE_URL", None) or f"https://app.{settings.PODCAST_WEBSITE_BASE_DOMAIN}"
    base_url = f"{frontend_domain}/podcast/{podcast_path}"
    feed_xml = _generate_podcast_rss(podcast, list(episodes), base_url)
    
    return Response(
        content=feed_xml,
        media_type="application/rss+xml",
        headers={
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
            "Content-Disposition": f'inline; filename="feed.xml"',
        }
    )


@router.get("/user/feed.xml", response_class=Response)
def get_user_first_podcast_feed(
    session: Session = Depends(get_session),
):
    """
    Convenience endpoint: RSS feed for user's first/primary podcast.
    Useful during migration when you have one podcast.
    """
    
    # Get first podcast (for single-podcast users)
    statement = select(Podcast).limit(1)
    podcast = session.exec(statement).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="No podcasts found")
    
    # Use slug if available, otherwise UUID
    identifier = podcast.slug or str(podcast.id)
    return get_podcast_feed(identifier, session)
