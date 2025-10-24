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
from api.services.op3_historical_data import get_historical_data

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/podcast/{podcast_id}/downloads")
async def get_podcast_downloads(
    podcast_id: UUID,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive download statistics for a podcast show from OP3.
    
    Uses cached OP3 data (3-hour TTL) to provide:
    - Total downloads for requested period
    - 7d/30d/365d/all-time breakdowns
    - Top episodes
    - Downloads trend (if available)
    - Geographic and app breakdowns (if available)
    
    Returns:
        - podcast_id, podcast_name
        - total_downloads: Downloads in requested time period
        - downloads_7d, downloads_30d, downloads_365d, downloads_all_time
        - top_episodes: Top performing episodes
        - downloads_by_day, top_countries, top_apps
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
    from api.core.config import settings
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get podcast slug or use ID as identifier
    identifier = getattr(podcast, 'slug', None) or str(podcast.id)
    
    # ALWAYS use production domain for RSS feed URL (dev uses localhost which breaks OP3 lookups)
    rss_url = f"https://podcastplusplus.com/rss/{identifier}/feed.xml"
    
    logger.info(f"Analytics request for podcast {podcast_id} - RSS URL: {rss_url}")
    
    # Use cached sync fetch (respects 3-hour cache)
    from api.services.op3_analytics import get_show_stats_sync
    
    try:
        stats = get_show_stats_sync(rss_url, days=days)
    except Exception as e:
        logger.error(f"OP3 stats fetch failed for {rss_url}: {e}", exc_info=True)
        # Return empty stats instead of failing completely
        stats = None
    
    if not stats or (hasattr(stats, 'downloads_30d') and stats.downloads_30d == 0 and stats.downloads_all_time == 0):
        logger.warning(f"No OP3 stats available for {rss_url} - checking historical fallback")
        
        # Try historical TSV fallback
        historical = get_historical_data()
        downloads_7d = historical.get_total_downloads(days=7)
        downloads_30d = historical.get_total_downloads(days=30)
        downloads_all_time = historical.get_total_downloads()
        
        if downloads_all_time > 0:
            logger.info(f"Historical fallback: 7d={downloads_7d}, 30d={downloads_30d}, all-time={downloads_all_time}")
            # Return historical stats
            return {
                "podcast_id": str(podcast_id),
                "podcast_name": podcast.name,
                "rss_url": rss_url,
                "period_days": days,
                "downloads_7d": downloads_7d,
                "downloads_30d": downloads_30d,
                "downloads_365d": 0,  # TSV doesn't have 365-day data
                "downloads_all_time": downloads_all_time,
                "total_downloads": downloads_30d if days == 30 else downloads_7d if days == 7 else downloads_all_time,
                "top_episodes": [],  # Could parse from TSV but keep simple for now
                "downloads_by_day": [],
                "weekly_downloads": [],
                "top_countries": [],
                "top_apps": [],
                "cached": True,
                "last_updated": "Historical data (pre-migration)",
                "note": "Showing historical analytics data. New downloads will be tracked in real-time once RSS feed is updated."
            }
        
        # No historical data either - return zeros
        logger.warning(f"No historical data available either - returning zero stats")
        return {
            "podcast_id": str(podcast_id),
            "podcast_name": podcast.name,
            "rss_url": rss_url,
            "period_days": days,
            "downloads_7d": 0,
            "downloads_30d": 0,
            "downloads_365d": 0,
            "downloads_all_time": 0,
            "total_downloads": 0,
            "top_episodes": [],
            "downloads_by_day": [],
            "weekly_downloads": [],
            "top_countries": [],
            "top_apps": [],
            "cached": False,
            "last_updated": "No data available yet",
            "note": "Analytics data will appear after your RSS feed has been published and episodes have been downloaded by listeners."
        }
    
    # Return comprehensive stats
    return {
        "podcast_id": str(podcast_id),
        "podcast_name": podcast.name,
        "rss_url": rss_url,
        "period_days": days,
        # Time period breakdowns
        "downloads_7d": stats.downloads_7d,
        "downloads_30d": stats.downloads_30d,
        "downloads_365d": stats.downloads_365d,
        "downloads_all_time": stats.downloads_all_time,
        # Legacy field for requested period (use 30d as baseline)
        "total_downloads": stats.downloads_30d if days == 30 else stats.downloads_7d if days == 7 else stats.downloads_all_time,
        # Top episodes
        "top_episodes": stats.top_episodes,
        # Trend data
        "downloads_by_day": stats.downloads_trend,
        "weekly_downloads": stats.weekly_downloads,
        # Breakdowns (not yet implemented in enhanced fetch)
        "top_countries": stats.top_countries,
        "top_apps": stats.top_apps,
        # Metadata
        "cached": True,  # All data comes from cache (3h TTL)
        "last_updated": "Updates every 3 hours"
    }


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
    
    # Get the episode's audio URL (OP3-prefixed, same as RSS feed)
    # OP3 tracks by the enclosure URL in the RSS feed
    if not episode.gcs_audio_path:
        raise HTTPException(status_code=404, detail="Episode has no audio file")
    
    # Generate the same URL that would be in the RSS feed (with OP3 prefix)
    from infrastructure.gcs import get_public_audio_url
    audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
    if not audio_url:
        raise HTTPException(status_code=500, detail="Failed to generate audio URL")
    
    # Add self-hosted OP3 prefix (same as RSS feed does)
    op3_url = f"https://analytics.podcastplusplus.com/e/{audio_url}"
    
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
    
    NOTE: This endpoint is currently deprecated in favor of the top_episodes data
    returned from /analytics/podcast/{id}/downloads which uses the enhanced
    OP3 API that doesn't require authentication for individual episodes.
    
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
    
    # Return empty for now - frontend should use top_episodes from main analytics endpoint
    # TODO: Remove this endpoint entirely after frontend migration complete
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"episodes-summary endpoint called (deprecated) - returning empty list")
    
    return {
        "podcast_id": str(podcast_id),
        "episodes": [],
        "note": "This endpoint is deprecated. Use /analytics/podcast/{id}/downloads which includes top_episodes data."
    }
