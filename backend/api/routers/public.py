from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Episode, EpisodeStatus, Podcast
from api.services.op3_analytics import get_show_stats_sync
from api.services.op3_historical_data import get_historical_data

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/podcast/{podcast_id}/analytics")
def public_podcast_analytics(
    podcast_id: str,
    session: Session = Depends(get_session),
):
    """
    Public analytics endpoint for podcast front page.

    Returns analytics data with smart time period filtering based on podcast age.
    No authentication required - public access.

    Time periods shown:
    - 7 days: if podcast exists >= 7 days
    - 30 days: if podcast exists >= 30 days
    - 365 days: if podcast exists >= 365 days
    - All-time: always shown
    - Don't repeat: if podcast is < 30 days, only show 7d and all-time
    """
    import logging
    
    logger = logging.getLogger(__name__)

    # Get podcast by ID or slug
    try:
        podcast_uuid = UUID(podcast_id)
        podcast = session.get(Podcast, podcast_uuid)
    except (ValueError, AttributeError):
        # Try by slug
        podcast = session.exec(
            select(Podcast).where(Podcast.slug == podcast_id)
        ).first()

    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Calculate podcast age (days since first episode or creation)
    # Use first episode publish date if available, otherwise use podcast creation date
    first_episode = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.status == EpisodeStatus.published)
        .order_by(Episode.publish_at.asc())  # type: ignore
        .limit(1)
    ).first()
    
    if first_episode and first_episode.publish_at:
        podcast_start_date = first_episode.publish_at
    else:
        # Use current time if no first episode (podcast is new)
        podcast_start_date = datetime.now(timezone.utc)
    
    # Calculate podcast age in days
    now = datetime.now(timezone.utc)
    if podcast_start_date.tzinfo is None:
        podcast_start_date = podcast_start_date.replace(tzinfo=timezone.utc)
    podcast_age_days = (now - podcast_start_date).days
    
    logger.info(f"Podcast {podcast_id} age: {podcast_age_days} days (start: {podcast_start_date})")
    
    # Get RSS feed URL
    identifier = getattr(podcast, 'slug', None) or str(podcast.id)
    rss_url = f"https://podcastplusplus.com/rss/{identifier}/feed.xml"
    
    # Fetch OP3 stats
    # Try public OP3.dev first (where data usually is), then fall back to self-hosted
    try:
        stats = get_show_stats_sync(rss_url, days=365, use_public=True)
        # If public OP3.dev has no data, try self-hosted
        if not stats or (stats.downloads_30d == 0 and stats.downloads_all_time == 0):
            logger.info(f"OP3: No data on public OP3.dev for {rss_url}, trying self-hosted...")
            stats = get_show_stats_sync(rss_url, days=365, use_public=False)
    except Exception as e:
        logger.error(f"OP3 stats fetch failed for {rss_url}: {e}", exc_info=True)
        stats = None
    
    # Merge with historical data (for Cinema IRL)
    historical = get_historical_data()
    historical_all_time = historical.get_total_downloads() if historical else 0
    
    # Merge all-time downloads
    op3_downloads_7d = stats.downloads_7d if stats else 0
    op3_downloads_30d = stats.downloads_30d if stats else 0
    op3_downloads_365d = stats.downloads_365d if stats else 0
    op3_downloads_all_time = stats.downloads_all_time if stats else 0

    merged_all_time = op3_downloads_all_time
    if historical_all_time > 0:
        podcast_identifier = getattr(podcast, 'slug', '').lower() or podcast.name.lower()
        if 'cinema' in podcast_identifier and 'irl' in podcast_identifier:
            logger.info(f"Merging historical data for Cinema IRL: historical={historical_all_time}, OP3={op3_downloads_all_time}")
            merged_all_time = historical_all_time + op3_downloads_all_time

    # Smart time period filtering based on podcast age
    # Don't repeat - if podcast is < 30 days, only show 7d and all-time
    time_periods = {}

    # Always show all-time
    time_periods["all_time"] = merged_all_time

    # Show 7d if podcast exists >= 7 days
    if podcast_age_days >= 7:
        time_periods["7d"] = op3_downloads_7d

    # Show 30d if podcast exists >= 30 days
    if podcast_age_days >= 30:
        time_periods["30d"] = op3_downloads_30d

    # Show 365d if podcast exists >= 365 days
    if podcast_age_days >= 365:
        time_periods["365d"] = op3_downloads_365d

    logger.info(f"Podcast {podcast_id} analytics - age: {podcast_age_days} days, periods: {list(time_periods.keys())}")

    return {
        "podcast_id": str(podcast.id),
        "podcast_name": podcast.name,
        "podcast_age_days": podcast_age_days,
        "time_periods": time_periods,
        "downloads_7d": op3_downloads_7d,
        "downloads_30d": op3_downloads_30d,
        "downloads_365d": op3_downloads_365d,
        "downloads_all_time": merged_all_time,
        "cached": True,
        "last_updated": "Updates every 3 hours"
    }
