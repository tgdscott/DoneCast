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
from api.billing.plans import can_access_analytics, get_analytics_level

router = APIRouter(prefix="/analytics", tags=["analytics"])


def assert_analytics_access(user: User, required_level: str = "basic") -> None:
    """
    Assert user has access to analytics at required level.
    
    Raises HTTPException(403) if access denied.
    
    Args:
        user: User object
        required_level: Required analytics level ("basic", "advanced", "full")
    """
    plan_key = getattr(user, 'tier', 'free') or 'free'
    
    if not can_access_analytics(plan_key, required_level):
        plan_level = get_analytics_level(plan_key)
        raise HTTPException(
            status_code=403,
            detail=(
                f"Analytics access denied. Your plan ({plan_key}) provides "
                f"{plan_level} analytics, but {required_level} is required. "
                f"Please upgrade your plan."
            )
        )


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
    
    # Check analytics access - allow basic for everyone, but filter response based on level
    # assert_analytics_access(current_user, "full")
    user_tier = getattr(current_user, 'tier', 'free') or 'free'
    analytics_level = get_analytics_level(user_tier)
    
    # Construct RSS feed URL for OP3 lookup
    from api.core.config import settings
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get podcast slug or use ID as identifier
    identifier = getattr(podcast, 'slug', None) or str(podcast.id)
    
    # Try multiple RSS feed URL variations (OP3 might have registered a different URL)
    # Order: current URL, then variations (with/without www, with/without /api)
    rss_url_variations = [
        f"https://podcastplusplus.com/rss/{identifier}/feed.xml",  # Current format
        f"https://www.podcastplusplus.com/rss/{identifier}/feed.xml",  # With www
        f"https://app.podcastplusplus.com/rss/{identifier}/feed.xml",  # App subdomain
        f"https://app.podcastplusplus.com/api/rss/{identifier}/feed.xml",  # With /api
        f"https://podcastplusplus.com/api/rss/{identifier}/feed.xml",  # With /api, no www
    ]
    
    # Also check if podcast has a stored rss_url (might be old Spreaker URL or different format)
    if hasattr(podcast, 'rss_url') and podcast.rss_url:
        rss_url_variations.insert(0, podcast.rss_url)  # Try stored URL first
    
    logger.info(f"Analytics request for podcast {podcast_id} - Trying RSS URLs: {rss_url_variations}")
    
    # Use cached sync fetch (respects 3-hour cache)
    # Try public OP3.dev first (where data usually is), then fall back to self-hosted
    from api.services.op3_analytics import get_show_stats_sync
    
    stats = None
    successful_url = None
    
    # Try public OP3.dev first (where the data is based on screenshot)
    for rss_url in rss_url_variations:
        try:
            logger.info(f"OP3: Trying public OP3.dev with RSS URL: {rss_url}")
            stats = get_show_stats_sync(rss_url, days=days, use_public=True)
            if stats and (stats.downloads_30d > 0 or stats.downloads_all_time > 0):
                successful_url = rss_url
                logger.info(f"OP3: ✅ Found data on public OP3.dev with URL: {rss_url}")
                logger.info(f"OP3: Stats - 7d={stats.downloads_7d}, 30d={stats.downloads_30d}, 365d={stats.downloads_365d}, all-time={stats.downloads_all_time}")
                break
            elif stats:
                logger.info(f"OP3: Public OP3.dev returned stats but no data for URL: {rss_url}")
        except Exception as e:
            logger.warning(f"OP3: Failed to fetch from public OP3.dev with URL {rss_url}: {e}")
            continue
    
    # If public OP3.dev has no data, try self-hosted OP3
    if not stats or (stats.downloads_30d == 0 and stats.downloads_all_time == 0):
        logger.info(f"OP3: No data on public OP3.dev, trying self-hosted OP3...")
        # Use the first URL variation (current format) for self-hosted
        rss_url = rss_url_variations[0]
        try:
            stats = get_show_stats_sync(rss_url, days=days, use_public=False)
            if stats and (stats.downloads_30d > 0 or stats.downloads_all_time > 0):
                successful_url = rss_url
                logger.info(f"OP3: ✅ Found data on self-hosted OP3 with URL: {rss_url}")
                logger.info(f"OP3: Stats - 7d={stats.downloads_7d}, 30d={stats.downloads_30d}, 365d={stats.downloads_365d}, all-time={stats.downloads_all_time}")
        except Exception as e:
            logger.error(f"OP3: Failed to fetch from self-hosted OP3 with URL {rss_url}: {e}")
            stats = None
    
    # Use the successful URL for merging (or first variation if none worked)
    rss_url = successful_url or rss_url_variations[0]
    logger.info(f"OP3: Using RSS URL: {rss_url} for data merge")
    
    # Check for Cinema IRL historical data merge
    # Historical data should be merged with OP3 data, not used as fallback only
    historical = get_historical_data()
    historical_all_time = historical.get_total_downloads() if historical else 0
    
    # Merge historical data with OP3 data
    # For time-windowed stats (7d, 30d, 365d), use OP3 data only (historical is old)
    # For all-time, merge historical all-time + OP3 all-time (since migration)
    op3_downloads_7d = stats.downloads_7d if stats else 0
    op3_downloads_30d = stats.downloads_30d if stats else 0
    op3_downloads_365d = stats.downloads_365d if stats else 0
    op3_downloads_all_time = stats.downloads_all_time if stats else 0
    
    # Merge all-time downloads: historical (pre-migration) + OP3 (post-migration)
    # Only merge if we have both historical and OP3 data for Cinema IRL
    merged_all_time = op3_downloads_all_time
    if historical_all_time > 0:
        # Check if this is Cinema IRL (by podcast name or slug)
        podcast_identifier = getattr(podcast, 'slug', '').lower() or podcast.name.lower()
        if 'cinema' in podcast_identifier and 'irl' in podcast_identifier:
            logger.info(f"Merging historical data for Cinema IRL: historical={historical_all_time}, OP3={op3_downloads_all_time}")
            # Historical data is pre-migration, OP3 data is post-migration
            # They should be additive, not overlapping
            # However, we need to be careful: if OP3 already includes historical data, don't double-count
            # For now, assume OP3 only tracks new downloads since migration, so add them together
            merged_all_time = historical_all_time + op3_downloads_all_time
            logger.info(f"Merged all-time downloads: {merged_all_time} (historical: {historical_all_time} + OP3: {op3_downloads_all_time})")
    
    # Merge top episodes: combine historical and OP3 episodes
    # Historical episodes are older, OP3 episodes are newer
    top_episodes = stats.top_episodes if stats else []
    if historical_all_time > 0 and hasattr(podcast, 'slug'):
        podcast_identifier = getattr(podcast, 'slug', '').lower() or podcast.name.lower()
        if 'cinema' in podcast_identifier and 'irl' in podcast_identifier:
            # Get top historical episodes
            historical_top = historical.get_top_episodes(limit=10, days=None)
            # Combine with OP3 top episodes
            # Create a dict to avoid duplicates (by title)
            episodes_dict = {}
            for ep in historical_top:
                episodes_dict[ep['episode_title']] = {
                    "title": ep['episode_title'],
                    "episode_id": None,  # Historical data doesn't have episode IDs
                    "downloads_1d": 0,
                    "downloads_3d": 0,
                    "downloads_7d": ep.get('downloads', 0),  # Use all-time as proxy
                    "downloads_30d": ep.get('downloads', 0),
                    "downloads_all_time": ep.get('downloads', 0),
                }
            # Add OP3 episodes (they will overwrite historical if same title, which is fine - OP3 is newer)
            for ep in top_episodes:
                ep_title = ep.get('title', '')
                if ep_title in episodes_dict:
                    # Merge: use OP3 all-time (newer data)
                    episodes_dict[ep_title]['downloads_all_time'] = max(
                        episodes_dict[ep_title]['downloads_all_time'],
                        ep.get('downloads_all_time', 0)
                    )
                else:
                    episodes_dict[ep_title] = ep
            # Sort by all-time downloads and take top 10
            top_episodes = sorted(
                episodes_dict.values(),
                key=lambda x: x.get('downloads_all_time', 0),
                reverse=True
            )[:10]
            logger.info(f"Merged top episodes: {len(top_episodes)} episodes (historical: {len(historical_top)}, OP3: {len(stats.top_episodes) if stats else 0})")
    
    # If no OP3 stats, fall back to historical only
    if not stats or (op3_downloads_30d == 0 and op3_downloads_all_time == 0):
        if historical_all_time > 0:
            logger.warning(f"No OP3 stats available for {rss_url} - using historical fallback")
            historical_7d = historical.get_total_downloads(days=7)
            historical_30d = historical.get_total_downloads(days=30)
            historical_top = historical.get_top_episodes(limit=10, days=None)
            
            return {
                "podcast_id": str(podcast_id),
                "podcast_name": podcast.name,
                "rss_url": rss_url,
                "period_days": days,
                "downloads_7d": historical_7d,
                "downloads_30d": historical_30d,
                "downloads_365d": 0,  # TSV doesn't have 365-day data
                "downloads_all_time": historical_all_time,
                "total_downloads": historical_30d if days == 30 else historical_7d if days == 7 else historical_all_time,
                "top_episodes": [
                    {
                        "title": ep['episode_title'],
                        "episode_id": None,
                        "downloads_1d": 0,
                        "downloads_3d": 0,
                        "downloads_7d": ep.get('downloads', 0),
                        "downloads_30d": ep.get('downloads', 0),
                        "downloads_all_time": ep.get('downloads', 0),
                    }
                    for ep in historical_top
                ],
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
    
    # Filter response based on analytics level
    response_data = {
        "podcast_id": str(podcast_id),
        "podcast_name": podcast.name,
        "rss_url": rss_url,
        "period_days": days,
        # Totals are available to all tiers
        "downloads_7d": op3_downloads_7d,
        "downloads_30d": op3_downloads_30d,
        "downloads_365d": op3_downloads_365d,
        "downloads_all_time": merged_all_time,
        "total_downloads": op3_downloads_30d if days == 30 else op3_downloads_7d if days == 7 else merged_all_time,
        "cached": True,
        "last_updated": "Updates every 3 hours",
        "analytics_level": analytics_level,
    }

    # Tier-specific data
    if analytics_level == "basic":
        # Basic: Totals + Top 3 episodes only, no charts/breakdowns
        response_data.update({
            "top_episodes": top_episodes[:3],
            "downloads_by_day": [],
            "weekly_downloads": [],
            "top_countries": [],
            "top_apps": [],
            "note": "Upgrade to Creator or Pro to view detailed charts, full episode lists, and audience breakdowns."
        })
    
    elif analytics_level == "advanced":
        # Advanced (Creator): Full charts (30d), Top 10 episodes, Top 5 breakdowns
        # OP3 stats are already usually limited to the requested window, but we ensure limits here
        response_data.update({
            "top_episodes": top_episodes[:10],
            "downloads_by_day": stats.downloads_trend if stats else [],
            "weekly_downloads": stats.weekly_downloads if stats else [],
            "top_countries": (stats.top_countries if stats else [])[:5],
            "top_apps": (stats.top_apps if stats else [])[:5],
            "note": "Upgrade to Pro for full audience insights and unlimited history."
        })
        
    else:
        # Full (Pro/Deluxe): Everything available
        response_data.update({
            "top_episodes": top_episodes,
            "downloads_by_day": stats.downloads_trend if stats else [],
            "weekly_downloads": stats.weekly_downloads if stats else [],
            "top_countries": stats.top_countries if stats else [],
            "top_apps": stats.top_apps if stats else [],
            "note": "All-time downloads include historical data (pre-migration) merged with new OP3 data (post-migration)." if historical_all_time > 0 else None
        })

    return response_data


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
    
    # Check analytics access (advanced analytics required for episode stats)
    assert_analytics_access(current_user, "advanced")
    
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



