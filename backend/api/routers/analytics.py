"""
Analytics API endpoints for podcast download statistics.

Integrates with OP3 (Open Podcast Prefix Project) to provide analytics data.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Podcast, Episode
from api.routers.auth import get_current_user
from api.models.user import User
from api.services.op3_analytics import OP3Analytics, OP3ShowStats, OP3EpisodeStats

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/podcast/{podcast_id}/downloads")
async def get_podcast_downloads(
    podcast_id: UUID,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get download statistics for a podcast show from OP3.
    
    Returns:
        - total_downloads: Total downloads in the time period
        - downloads_trend: Daily download counts
        - top_countries: Geographic breakdown
        - top_apps: Podcast app breakdown
    """
    # Get podcast and verify ownership
    podcast = session.get(Podcast, podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Verify user owns this podcast
    if podcast.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view analytics for this podcast"
        )
    
    # Construct RSS feed URL for OP3 lookup
    # This should match the URL that podcast apps use
    from api.core.config import settings
    
    # Try to get the canonical RSS URL
    # Option 1: If podcast has a custom domain/URL
    if hasattr(podcast, 'feed_url') and podcast.feed_url:
        rss_url = podcast.feed_url
    # Option 2: Use our own RSS feed URL
    else:
        # Get podcast slug or use ID
        identifier = getattr(podcast, 'slug', None) or str(podcast.id)
        rss_url = f"{settings.BASE_URL}/v1/rss/{identifier}/feed.xml"
    
    # Fetch stats from OP3
    start_date = datetime.utcnow() - timedelta(days=days)
    client = OP3Analytics()
    try:
        stats = await client.get_show_downloads(
            show_url=rss_url,
            start_date=start_date,
        )
        return {
            "podcast_id": str(podcast_id),
            "podcast_name": podcast.name,
            "rss_url": rss_url,
            "period_days": days,
            "total_downloads": stats.total_downloads,
            "downloads_by_day": stats.downloads_trend,
            "top_countries": stats.top_countries,
            "top_apps": stats.top_apps,
        }
    finally:
        await client.close()


@router.get("/episode/{episode_id}/downloads")
async def get_episode_downloads(
    episode_id: UUID,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get download statistics for a specific episode from OP3.
    
    Returns:
        - downloads_24h: Downloads in last 24 hours
        - downloads_7d: Downloads in last 7 days
        - downloads_30d: Downloads in last 30 days
        - downloads_total: Total downloads (all time in the requested period)
    """
    # Get episode and verify ownership
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Get podcast to verify ownership
    podcast = session.get(Podcast, episode.podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Verify user owns this podcast (and therefore the episode)
    if podcast.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view analytics for this episode"
        )
    
    # Get the episode's audio URL (OP3-prefixed)
    # OP3 tracks by the enclosure URL in the RSS feed
    if not episode.gcs_audio_path:
        raise HTTPException(status_code=404, detail="Episode has no audio file")
    
    # Generate the same URL that would be in the RSS feed
    from infrastructure.gcs import get_public_audio_url
    audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
    if not audio_url:
        raise HTTPException(status_code=500, detail="Failed to generate audio URL")
    
    # Add OP3 prefix (same as RSS feed does)
    op3_url = f"https://op3.dev/e/{audio_url}"
    
    # Fetch stats from OP3
    start_date = datetime.utcnow() - timedelta(days=days)
    client = OP3Analytics()
    try:
        stats = await client.get_episode_downloads(
            episode_url=op3_url,
            start_date=start_date,
        )
        return {
            "episode_id": str(episode_id),
            "episode_title": episode.title,
            "episode_number": episode.episode_number,
            "period_days": days,
            "downloads_24h": stats.downloads_24h,
            "downloads_7d": stats.downloads_7d,
            "downloads_30d": stats.downloads_30d,
            "downloads_total": stats.downloads_total,
        }
    finally:
        await client.close()


@router.get("/podcast/{podcast_id}/episodes-summary")
async def get_podcast_episodes_summary(
    podcast_id: UUID,
    limit: int = Query(default=10, ge=1, le=100, description="Number of episodes to include"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get download summary for multiple episodes in a podcast.
    
    Returns a list of episodes with their download stats.
    Useful for dashboard "Top Episodes" widgets.
    """
    # Get podcast and verify ownership
    podcast = session.get(Podcast, podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Verify user owns this podcast
    if podcast.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view analytics for this podcast"
        )
    
    # Get recent published episodes
    from api.models.podcast import EpisodeStatus
    stmt = (
        select(Episode)
        .where(Episode.podcast_id == podcast_id)
        .where(Episode.status == EpisodeStatus.published)
        .where(Episode.gcs_audio_path.is_not(None))
        .order_by(Episode.publish_at.desc())
        .limit(limit)
    )
    episodes = session.exec(stmt).all()
    
    if not episodes:
        return {
            "podcast_id": str(podcast_id),
            "episodes": [],
        }
    
    # Generate OP3 URLs for all episodes
    from infrastructure.gcs import get_public_audio_url
    episode_urls = []
    episode_map = {}
    
    for episode in episodes:
        if episode.gcs_audio_path:
            audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
            if audio_url:
                op3_url = f"https://op3.dev/e/{audio_url}"
                episode_urls.append(op3_url)
                episode_map[op3_url] = episode
    
    # Fetch stats for all episodes in parallel
    client = OP3Analytics()
    try:
        start_date = datetime.utcnow() - timedelta(days=30)
        stats_list = await client.get_multiple_episodes(
            episode_urls,
            start_date=start_date,
        )
        
        # Build response
        results = []
        for url, stats in zip(episode_urls, stats_list):
            if isinstance(stats, Exception):
                continue  # Skip failed requests
            
            episode = episode_map[url]
            results.append({
                "episode_id": str(episode.id),
                "title": episode.title,
                "episode_number": episode.episode_number,
                "publish_date": episode.publish_at.isoformat() if episode.publish_at else None,
                "downloads_24h": stats.downloads_24h,
                "downloads_7d": stats.downloads_7d,
                "downloads_30d": stats.downloads_30d,
                "downloads_total": stats.downloads_total,
            })
        
        # Sort by total downloads descending
        results.sort(key=lambda x: x["downloads_total"], reverse=True)
        
        return {
            "podcast_id": str(podcast_id),
            "episodes": results,
        }
    finally:
        await client.close()
