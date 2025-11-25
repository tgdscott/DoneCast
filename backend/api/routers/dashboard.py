from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
import re

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlmodel import Session, select, desc

from api.routers.auth import get_current_user
from api.core.database import get_session
from api.models.podcast import Episode, EpisodeStatus, Podcast
from api.models.user import User
from api.services.publisher import SpreakerClient
from api.services.op3_analytics import get_show_stats_sync, OP3ShowStats
from api.services.op3_historical_data import get_historical_data

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _parse_spreaker_datetime(value: Optional[object]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith('Z'):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_int(value: Optional[object]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _compute_local_episode_stats(session: Session, user_id) -> tuple[dict, int]:
    now = datetime.now(timezone.utc)

    # CRITICAL: Exclude placeholder episodes (episode_number=0) - they're ONLY for RSS feeds, never shown to users
    total_episodes = session.exec(
        select(func.count(Episode.id))
        .where(Episode.user_id == user_id)
        .where(or_(Episode.episode_number != 0, Episode.episode_number == None))  # Exclude placeholder episodes (0), allow NULL
    ).one()

    upcoming_scheduled = session.exec(
        select(func.count(Episode.id)).where(
            Episode.user_id == user_id,
            or_(Episode.episode_number != 0, Episode.episode_number == None),  # Exclude placeholder episodes (0), allow NULL
            Episode.publish_at != None,  # noqa: E711
            Episode.publish_at > now,
        )
    ).one()

    # Get the most recently PUBLISHED episode (by publish_at, regardless of status if publish_at is in the past)
    # Episodes with past publish_at dates are considered published even if status is "processed"
    # IMPORTANT: Order by publish_at DESC to get the MOST RECENT episode
    last_published_episode = session.exec(
        select(Episode)
        .where(Episode.user_id == user_id)
        .where(or_(Episode.episode_number != 0, Episode.episode_number == None))  # Exclude placeholder episodes (0), allow NULL
        .where(Episode.publish_at != None)  # noqa: E711
        .where(Episode.publish_at <= now)  # Only published episodes (not scheduled)
        .order_by(desc(Episode.publish_at))
        .limit(1)
    ).first()

    last_published_at = None
    if last_published_episode and last_published_episode.publish_at:
        pub_dt = last_published_episode.publish_at
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        else:
            pub_dt = pub_dt.astimezone(timezone.utc)
        last_published_at = pub_dt.isoformat().replace('+00:00', 'Z')
        logger.debug(f"[DASHBOARD] Last published episode: {last_published_episode.title} - publish_at: {pub_dt.isoformat()} (UTC)")
        # Calculate days ago for logging
        days_ago = (now - pub_dt).days
        logger.debug(f"[DASHBOARD] Last published episode is {days_ago} days ago")
    else:
        logger.warning(f"[DASHBOARD] No published episodes found for user {user_id}")

    # Get the most recently PROCESSED episode (for assembly status)
    last_processed_episode = session.exec(
        select(Episode)
        .where(Episode.user_id == user_id)
        .where(or_(Episode.episode_number != 0, Episode.episode_number == None))  # Exclude placeholder episodes (0), allow NULL
        .where(Episode.processed_at != None)  # noqa: E711
        .order_by(desc(Episode.processed_at))
        .limit(1)
    ).first()

    last_status = None
    if last_processed_episode:
        status_val = getattr(last_processed_episode, "status", None)
        if status_val == EpisodeStatus.error:
            last_status = 'error'
        elif status_val in (EpisodeStatus.processed, EpisodeStatus.published):
            last_status = 'success'
        elif status_val in (EpisodeStatus.pending, EpisodeStatus.processing):
            last_status = 'pending'
        elif status_val is not None:
            last_status = str(status_val)

    since = now - timedelta(days=30)
    # Count episodes with past publish_at (regardless of status) as published
    episodes_last_30d = session.exec(
        select(func.count(Episode.id)).where(
            Episode.user_id == user_id,
            Episode.publish_at != None,  # noqa: E711
            Episode.publish_at >= since,
            Episode.publish_at <= now,  # Only count PAST episodes, not future scheduled ones
        )
    ).one()
    
    # Get 3 most recent episodes (by publish_at, regardless of status if publish_at is in the past)
    # Use SQLAlchemy text() for reliable ordering with NULL handling
    from sqlalchemy import text as sa_text
    recent_episodes = session.exec(
        select(Episode)
        .where(Episode.user_id == user_id)
        .where(or_(Episode.episode_number != 0, Episode.episode_number == None))  # Exclude placeholder episodes (0), allow NULL
        .where(Episode.publish_at != None)  # noqa: E711
        .where(Episode.publish_at <= now)  # Only published episodes (not scheduled)
        .order_by(sa_text("publish_at DESC"))
        .limit(3)
    ).all()
    
    # Format recent episodes for frontend (downloads will be added later from OP3)
    recent_episodes_data = []
    for ep in recent_episodes:
        if ep and ep.publish_at:
            pub_dt = ep.publish_at
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            else:
                pub_dt = pub_dt.astimezone(timezone.utc)
            recent_episodes_data.append({
                "episode_id": str(ep.id),
                "title": ep.title or "Untitled",
                "publish_at": pub_dt.isoformat().replace('+00:00', 'Z'),
                "downloads_all_time": 0,  # Will be populated from OP3 or historical data
            })
            logger.debug(f"[DASHBOARD] Recent episode: {ep.title} - publish_at: {pub_dt.isoformat()} (UTC)")

    base = {
        "total_episodes": int(total_episodes or 0),
        "upcoming_scheduled": int(upcoming_scheduled or 0),
        "last_published_at": last_published_at,
        "last_assembly_status": last_status,
        "recent_episodes": recent_episodes_data,  # Most recent 3 episodes
    }
    logger.debug(f"[DASHBOARD] Base stats - last_published_at: {last_published_at}, recent_episodes: {len(recent_episodes_data)}")
    return base, int(episodes_last_30d or 0)


@router.get("/stats")
def dashboard_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard statistics combining local database and OP3 analytics.
    
    Returns:
        - Episode counts from local database
        - Download/play stats from OP3 if available
        - Graceful fallback to local counts if OP3 unavailable
    """
    # Always compute local stats as baseline
    try:
        base_stats, local_last_30d = _compute_local_episode_stats(session, current_user.id)
    except Exception as e:
        logger.error(f"Failed to compute local episode stats: {e}", exc_info=True)
        # CRITICAL: Rollback the session if a database error occurred
        # This prevents "transaction is aborted" errors on subsequent queries
        try:
            session.rollback()
        except Exception as rollback_exc:
            logger.warning(f"Failed to rollback session after error: {rollback_exc}")
        # If local aggregation fails, degrade gracefully
        base_stats, local_last_30d = ({
            "total_episodes": 0,
            "upcoming_scheduled": 0,
            "last_published_at": None,
            "last_assembly_status": None,
        }, 0)
    
    # Try to fetch OP3 analytics for enhanced stats
    op3_downloads_30d = None
    op3_downloads_7d = None
    op3_downloads_365d = None
    op3_downloads_all_time = None
    op3_top_episodes = []
    op3_show_stats = None
    op3_error_message = None
    op3_episode_stats_map = {}  # Map episode titles to download counts (will be populated from OP3 and historical)
    historical_episode_map = {}  # Map historical episode titles to download counts
    
    try:
        # Get user's primary podcast RSS feed URL
        # Most users have one podcast, just grab the first one
        podcasts = session.exec(
            select(Podcast).where(Podcast.user_id == current_user.id).limit(1)
        ).all()
        
        podcast = podcasts[0] if podcasts else None
        
        if not podcast:
            logger.info("No podcast found for user - skipping OP3 stats")
            op3_error_message = "No podcast configured"
        elif not podcast.rss_feed_url:
            logger.warning(f"Podcast {podcast.id} has no RSS feed URL - cannot fetch OP3 stats")
            op3_error_message = "RSS feed not configured"
        else:
            rss_url = podcast.rss_feed_url
            logger.debug(f"Fetching OP3 stats for RSS feed: {rss_url}")
            
            # Try multiple RSS feed URL variations (OP3 might have registered a different URL)
            # This matches the logic in analytics.py
            identifier = getattr(podcast, 'slug', None) or str(podcast.id)
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
            
            logger.debug(f"Dashboard: Trying RSS URLs for OP3: {rss_url_variations}")
            
            # For Cinema IRL, use known show UUID (from OP3.dev screenshot)
            # Show UUID: 285fa80eafd64305b99386b3f7184f88
            podcast_identifier = getattr(podcast, 'slug', '').lower() or podcast.name.lower()
            known_show_uuid = None
            if 'cinema' in podcast_identifier and 'irl' in podcast_identifier:
                known_show_uuid = "285fa80eafd64305b99386b3f7184f88"
                logger.debug(f"Cinema IRL detected - using known show UUID: {known_show_uuid}")
            
            # Use sync wrapper to fetch OP3 stats (handles async internally)
            # Try public OP3.dev first (where data usually is), then fall back to self-hosted
            # If we have a known show UUID, use it directly (bypasses RSS URL lookup)
            op3_show_stats = None
            successful_url = None
            
            # If we have a known show UUID, try it first with the primary RSS URL
            if known_show_uuid:
                primary_rss_url = rss_url_variations[0]
                try:
                    logger.debug(f"OP3: Trying known show UUID {known_show_uuid} with RSS URL: {primary_rss_url}")
                    stats = get_show_stats_sync(primary_rss_url, days=30, use_public=True, show_uuid=known_show_uuid)
                    if stats and (stats.downloads_30d > 0 or stats.downloads_all_time > 0):
                        op3_show_stats = stats
                        successful_url = primary_rss_url
                        logger.info(f"OP3: ✅ Found data using known show UUID - 7d={stats.downloads_7d}, 30d={stats.downloads_30d}, all-time={stats.downloads_all_time}")
                    elif stats:
                        logger.debug(f"OP3: Known show UUID returned stats but no data, trying RSS URL variations...")
                except Exception as e:
                    logger.debug(f"OP3: Failed to fetch with known show UUID: {e}, trying RSS URL variations...")
            
            # If known UUID didn't work or we don't have one, try RSS URL variations (stop early when data found)
            if not op3_show_stats or (op3_show_stats.downloads_30d == 0 and op3_show_stats.downloads_all_time == 0):
                # Try public OP3.dev with RSS URL variations (stop on first success)
                for rss_url_var in rss_url_variations:
                    try:
                        logger.debug(f"OP3: Trying public OP3.dev with RSS URL: {rss_url_var}")
                        stats = get_show_stats_sync(rss_url_var, days=30, use_public=True)
                        if stats and (stats.downloads_30d > 0 or stats.downloads_all_time > 0):
                            op3_show_stats = stats
                            successful_url = rss_url_var
                            logger.info(f"OP3: ✅ Found data on public OP3.dev - 7d={stats.downloads_7d}, 30d={stats.downloads_30d}, all-time={stats.downloads_all_time}")
                            break  # Stop trying once we find data
                    except Exception as e:
                        logger.debug(f"OP3: Failed to fetch from public OP3.dev with URL {rss_url_var}: {e}")
                        continue
                
                # If public OP3.dev has no data, try self-hosted OP3 (only once, not for each URL)
                if not op3_show_stats or (op3_show_stats.downloads_30d == 0 and op3_show_stats.downloads_all_time == 0):
                    logger.debug(f"OP3: No data on public OP3.dev, trying self-hosted OP3...")
                    # Use the first URL variation (current format) for self-hosted
                    rss_url_var = rss_url_variations[0]
                    try:
                        stats = get_show_stats_sync(rss_url_var, days=30, use_public=False, show_uuid=known_show_uuid)
                        if stats and (stats.downloads_30d > 0 or stats.downloads_all_time > 0):
                            op3_show_stats = stats
                            successful_url = rss_url_var
                            logger.info(f"OP3: ✅ Found data on self-hosted OP3 - 7d={stats.downloads_7d}, 30d={stats.downloads_30d}, all-time={stats.downloads_all_time}")
                    except Exception as e:
                        logger.debug(f"OP3: Failed to fetch from self-hosted OP3: {e}")
            
            # Use the successful URL (or first variation if none worked)
            rss_url = successful_url or rss_url_variations[0]
            logger.debug(f"OP3: Using RSS URL: {rss_url} for data merge")
            
            # ALWAYS set OP3 values (even if 0) so frontend can display them
            op3_episode_stats_map = {}  # Map episode titles to download counts (will be populated from OP3 and historical)
            if op3_show_stats:
                op3_downloads_7d = op3_show_stats.downloads_7d or 0
                op3_downloads_30d = op3_show_stats.downloads_30d or 0
                op3_downloads_365d = op3_show_stats.downloads_365d or 0
                op3_downloads_all_time = op3_show_stats.downloads_all_time or 0
                op3_top_episodes = op3_show_stats.top_episodes[:3] if op3_show_stats.top_episodes else []  # Top 3
                
                # Build map of episode titles to download counts for matching with recent episodes
                # Use all_episodes_map if available (has ALL episodes), otherwise fall back to top_episodes
                if hasattr(op3_show_stats, 'all_episodes_map') and op3_show_stats.all_episodes_map:
                    op3_episode_stats_map = op3_show_stats.all_episodes_map.copy()
                    logger.debug(f"[DASHBOARD] Built OP3 episode map from all_episodes_map with {len(op3_episode_stats_map)} episodes")
                elif op3_show_stats.top_episodes:
                    # Fallback: build map from top episodes only
                    for ep_stat in op3_show_stats.top_episodes:
                        title = ep_stat.get('title', '').strip().lower()
                        if title:
                            op3_episode_stats_map[title] = ep_stat.get('downloads_all_time', 0)
                    logger.debug(f"[DASHBOARD] Built OP3 episode map from top_episodes with {len(op3_episode_stats_map)} episodes")
                else:
                    logger.debug(f"[DASHBOARD] No OP3 episode data available for mapping")
                
                # CRITICAL FIX: If show-level stats are 0 but we have episode-level data, aggregate from episodes
                # This happens when OP3 returns episode data but show-level stats are incomplete/zero
                if (op3_downloads_7d == 0 and op3_downloads_30d == 0 and op3_downloads_365d == 0 and op3_downloads_all_time == 0) and op3_episode_stats_map:
                    logger.debug(f"[DASHBOARD] OP3 show-level stats are 0, attempting to recover from episode data...")
                    
                    # First, check if OP3 returned weekly_downloads that we can use for 7d/30d/365d
                    # (OP3 might return weekly data even if monthlyDownloads/downloads_7d are 0)
                    if hasattr(op3_show_stats, 'weekly_downloads') and op3_show_stats.weekly_downloads:
                        weekly_list = op3_show_stats.weekly_downloads
                        # Calculate 7d from weekly data (last 7 days)
                        if len(weekly_list) >= 7:
                            op3_downloads_7d = sum(weekly_list[-7:])
                        # Calculate 30d from weekly data (last 30 days)
                        if len(weekly_list) >= 30:
                            op3_downloads_30d = sum(weekly_list[-30:])
                        elif len(weekly_list) > 0:
                            # Use all available data as proxy for 30d
                            op3_downloads_30d = sum(weekly_list)
                        # Calculate 365d from weekly data
                        if len(weekly_list) >= 365:
                            op3_downloads_365d = sum(weekly_list[-365:])
                        elif len(weekly_list) > 0:
                            op3_downloads_365d = sum(weekly_list)
                        # Use sum of all weekly data as all-time proxy
                        if len(weekly_list) > 0:
                            op3_downloads_all_time = sum(weekly_list)
                    
                    # If weekly data didn't help, try aggregating from episode data
                    if op3_downloads_all_time == 0:
                        aggregated_all_time = sum(op3_episode_stats_map.values())
                        if aggregated_all_time > 0:
                            op3_downloads_all_time = aggregated_all_time
                            # For 365d, use all-time as proxy if we don't have it from weekly data
                            if op3_downloads_365d == 0:
                                op3_downloads_365d = aggregated_all_time
                
                if op3_downloads_30d > 0 or op3_downloads_all_time > 0:
                    logger.debug(f"OP3 stats: 7d={op3_downloads_7d}, 30d={op3_downloads_30d}, 365d={op3_downloads_365d}, all-time={op3_downloads_all_time}")
                else:
                    logger.debug(f"OP3 returned 0 downloads for {rss_url} - will try historical fallback")
            else:
                logger.debug("OP3 stats fetch returned None - will try historical fallback")
                op3_downloads_7d = 0
                op3_downloads_30d = 0
                op3_downloads_365d = 0
                op3_downloads_all_time = 0
                op3_top_episodes = []
            
            # FALLBACK: If OP3 has no data (0 or None), use historical TSV for Cinema IRL
            # This preserves the historical data that was there before
            # ALSO: Always include historical top episodes if available (even if OP3 has data)
            historical = get_historical_data()
            historical_episode_map = {}  # Map episode titles to historical download counts
            if historical:
                historical_7d = historical.get_total_downloads(days=7)
                historical_30d = historical.get_total_downloads(days=30)
                historical_all_time = historical.get_total_downloads()
                
                # Build map of historical episode downloads (for matching with recent episodes)
                all_historical_episodes = historical.get_all_episodes()
                for ep in all_historical_episodes:
                    title = ep.get('episode_title', '').strip().lower()
                    if title:
                        # Historical data uses 'downloads_all' not 'downloads_all_time'
                        downloads = ep.get('downloads_all', 0) or ep.get('downloads', 0)
                        historical_episode_map[title] = downloads
                logger.debug(f"[DASHBOARD] Built historical episode map with {len(historical_episode_map)} episodes")
                
                # Only use historical if it has data (Cinema IRL)
                if historical_all_time > 0:
                    logger.debug(f"Historical data available: 7d={historical_7d}, 30d={historical_30d}, all-time={historical_all_time}")
                    
                    # Merge: use historical if OP3 is 0, otherwise keep OP3
                    # IMPORTANT: For Cinema IRL, historical data should ALWAYS be used if OP3 has no data
                    if op3_downloads_all_time == 0:
                        logger.debug("Historical fallback ACTIVATED - OP3 has no data, using historical data")
                        if op3_downloads_7d == 0:
                            op3_downloads_7d = historical_7d
                        if op3_downloads_30d == 0:
                            op3_downloads_30d = historical_30d
                        if op3_downloads_all_time == 0:
                            op3_downloads_all_time = historical_all_time
                        op3_error_message = None  # Clear error since we have historical data
                    
                    # Merge historical episode map into OP3 episode map (prefer OP3, fallback to historical)
                    for title, downloads in historical_episode_map.items():
                        if title not in op3_episode_stats_map:
                            op3_episode_stats_map[title] = downloads
                    logger.debug(f"[DASHBOARD] Merged historical into OP3 episode map - total: {len(op3_episode_stats_map)} episodes")
                    
                    # ALWAYS get top episodes from historical if available (even if OP3 has data)
                    # Historical episodes are older and might have more downloads
                    top_historical = historical.get_top_episodes(limit=10, days=None)  # Get more for matching
                    if top_historical:
                        # Merge with OP3 top episodes (prefer OP3 for recent episodes, historical for older)
                        if op3_top_episodes:
                            # Combine both lists, deduplicate by title, prefer OP3 data for same title
                            episodes_dict = {}
                            for ep in op3_top_episodes:
                                title_key = ep.get('title', '').strip().lower()
                                if title_key:
                                    episodes_dict[title_key] = ep
                            # Add historical episodes that aren't in OP3
                            for ep in top_historical:
                                title_key = ep.get('episode_title', '').strip().lower()
                                if title_key and title_key not in episodes_dict:
                                    episodes_dict[title_key] = {
                                        'title': ep.get('episode_title', ''),
                                        'downloads_all_time': ep.get('downloads', 0),
                                        'episode_id': None
                                    }
                            op3_top_episodes = sorted(
                                episodes_dict.values(),
                                key=lambda x: x.get('downloads_all_time', 0),
                                reverse=True
                            )[:3]
                        else:
                            # No OP3 top episodes, use historical
                            op3_top_episodes = [
                                {
                                    'title': ep['episode_title'],
                                    'downloads_all_time': ep.get('downloads', 0),
                                    'episode_id': None
                                }
                                for ep in top_historical[:3]
                            ]
                        logger.debug(f"Merged top episodes: {len(op3_top_episodes)} episodes")
                else:
                    logger.debug("Historical data empty - showing zeros")
            else:
                logger.debug("No historical data available")
                historical_episode_map = {}  # Initialize empty if no historical data
            
    except Exception as e:
        # OP3 fetch failed - log but don't crash dashboard
        logger.error(f"Failed to fetch OP3 analytics: {e}", exc_info=True)
        # CRITICAL: Rollback the session if a database error occurred
        # This prevents "transaction is aborted" errors on subsequent queries
        error_str = str(e).lower()
        if "transaction" in error_str or "aborted" in error_str or "database" in error_str:
            try:
                session.rollback()
                logger.info("Rolled back session after database error in OP3 fetch")
            except Exception as rollback_exc:
                logger.warning(f"Failed to rollback session after OP3 error: {rollback_exc}")
        op3_error_message = f"API error: {str(e)}"
        logger.info("Falling back to local episode counts")
        # Initialize OP3 values to 0 if not already set
        if 'op3_downloads_7d' not in locals():
            op3_downloads_7d = 0
        if 'op3_downloads_30d' not in locals():
            op3_downloads_30d = 0
        if 'op3_downloads_365d' not in locals():
            op3_downloads_365d = 0
        if 'op3_downloads_all_time' not in locals():
            op3_downloads_all_time = 0
        if 'op3_top_episodes' not in locals():
            op3_top_episodes = []
        if 'op3_episode_stats_map' not in locals():
            op3_episode_stats_map = {}
        if 'historical_episode_map' not in locals():
            historical_episode_map = {}
        # Try to load historical data even if OP3 failed
        try:
            historical = get_historical_data()
            if historical:
                historical_all_time = historical.get_total_downloads()
                if historical_all_time > 0:
                    logger.info(f"OP3 failed but historical data available: all-time={historical_all_time}")
                    if op3_downloads_all_time == 0:
                        op3_downloads_all_time = historical_all_time
                        op3_downloads_7d = historical.get_total_downloads(days=7)
                        op3_downloads_30d = historical.get_total_downloads(days=30)
                        # Build historical episode map
                        all_historical_episodes = historical.get_all_episodes()
                        for ep in all_historical_episodes:
                            title = ep.get('episode_title', '').strip().lower()
                            if title:
                                downloads = ep.get('downloads_all', 0) or ep.get('downloads', 0)
                                historical_episode_map[title] = downloads
                        op3_episode_stats_map.update(historical_episode_map)
        except Exception as hist_ex:
            logger.warning(f"Failed to load historical data after OP3 error: {hist_ex}")
    
    # ALWAYS return all time period fields at root level (frontend expects these)
    # Frontend checks for: plays_7d, plays_30d, plays_365d, plays_all_time, plays_last_30d
    # Set to 0 if None to ensure fields are always present
    op3_downloads_7d = op3_downloads_7d if op3_downloads_7d is not None else 0
    op3_downloads_30d = op3_downloads_30d if op3_downloads_30d is not None else 0
    op3_downloads_365d = op3_downloads_365d if op3_downloads_365d is not None else 0
    op3_downloads_all_time = op3_downloads_all_time if op3_downloads_all_time is not None else 0
    
    # FINAL CHECK: If we still have zeros and historical data exists, use it
    # This ensures historical data is ALWAYS used for Cinema IRL when OP3 has no data
    if op3_downloads_all_time == 0:
        try:
            historical = get_historical_data()
            if historical:
                historical_all_time = historical.get_total_downloads()
                if historical_all_time > 0:
                    logger.debug(f"[DASHBOARD] FINAL CHECK: OP3 has 0 downloads, using historical data: all-time={historical_all_time}")
                    op3_downloads_all_time = historical_all_time
                    op3_downloads_7d = historical.get_total_downloads(days=7) if op3_downloads_7d == 0 else op3_downloads_7d
                    op3_downloads_30d = historical.get_total_downloads(days=30) if op3_downloads_30d == 0 else op3_downloads_30d
                    # Ensure episode maps are populated
                    if not op3_episode_stats_map or len(op3_episode_stats_map) == 0:
                        all_historical_episodes = historical.get_all_episodes()
                        for ep in all_historical_episodes:
                            title = ep.get('episode_title', '').strip().lower()
                            if title:
                                downloads = ep.get('downloads_all', 0) or ep.get('downloads', 0)
                                op3_episode_stats_map[title] = downloads
                        logger.debug(f"[DASHBOARD] FINAL CHECK: Populated episode map from historical data: {len(op3_episode_stats_map)} episodes")
                    # Also ensure historical_episode_map is populated for matching
                    if 'historical_episode_map' not in locals() or not historical_episode_map:
                        historical_episode_map = {}
                        all_historical_episodes = historical.get_all_episodes()
                        for ep in all_historical_episodes:
                            title = ep.get('episode_title', '').strip().lower()
                            if title:
                                downloads = ep.get('downloads_all', 0) or ep.get('downloads', 0)
                                historical_episode_map[title] = downloads
                        logger.debug(f"[DASHBOARD] FINAL CHECK: Populated historical_episode_map: {len(historical_episode_map)} episodes")
        except Exception as final_ex:
            logger.warning(f"Failed to load historical data in final check: {final_ex}")
    
    # Match recent episodes with download counts from OP3 or historical data
    # Do this AFTER all OP3 and historical data processing is complete
    # Update recent_episodes_data with download counts
    # Helper function to normalize titles for matching (removes special chars, normalizes whitespace)
    def normalize_title(title: str) -> str:
        """Normalize title for matching by removing special chars and normalizing whitespace."""
        if not title:
            return ""
        # Convert to lowercase and strip
        normalized = str(title).strip().lower()
        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized)
        # Remove common punctuation that might differ (quotes, apostrophes, etc.)
        # Use Unicode escape sequences for special characters
        normalized = normalized.replace('"', '').replace("'", '')
        normalized = normalized.replace('\u2018', '').replace('\u2019', '')  # Smart quotes
        normalized = normalized.replace('\u201c', '').replace('\u201d', '')  # Smart double quotes
        normalized = normalized.replace('\u2013', '-').replace('\u2014', '-')  # En/em dashes
        return normalized.strip()
    
    for ep_data in base_stats.get('recent_episodes', []):
        ep_title_raw = ep_data.get('title', '').strip()
        ep_title_normalized = normalize_title(ep_title_raw)
        # Try OP3 first (includes merged historical), then historical directly as fallback
        # Try exact match first, then normalized match
        downloads = 0
        if op3_episode_stats_map:
            # Try exact lowercase match first
            downloads = op3_episode_stats_map.get(ep_title_raw.lower(), 0)
            # If no match, try normalized match
            if downloads == 0:
                for op3_title, op3_downloads in op3_episode_stats_map.items():
                    if normalize_title(op3_title) == ep_title_normalized:
                        downloads = op3_downloads
                        logger.debug(f"[DASHBOARD] ✅ Matched via normalized title: '{ep_title_raw}' <-> '{op3_title}'")
                        break
        # Try historical data if OP3 didn't have it
        if downloads == 0 and historical_episode_map:
            # Try exact match first
            downloads = historical_episode_map.get(ep_title_raw.lower(), 0)
            # If no match, try normalized match
            if downloads == 0:
                for hist_title, hist_downloads in historical_episode_map.items():
                    if normalize_title(hist_title) == ep_title_normalized:
                        downloads = hist_downloads
                        logger.debug(f"[DASHBOARD] ✅ Matched via normalized title (historical): '{ep_title_raw}' <-> '{hist_title}'")
                        break
        ep_data['downloads_all_time'] = downloads
        if downloads > 0:
            logger.debug(f"[DASHBOARD] ✅ Matched recent episode '{ep_title_raw}' with {downloads} downloads")
        else:
            logger.debug(f"[DASHBOARD] ⚠️ No download data found for recent episode '{ep_title_raw}'")
    
    # Debug logging to diagnose missing stats
    logger.debug(f"[DASHBOARD] Final Stats - 7d: {op3_downloads_7d}, 30d: {op3_downloads_30d}, 365d: {op3_downloads_365d}, all-time: {op3_downloads_all_time}")
    
    # Build response with OP3 data - ALWAYS include all fields at root level
    return {
        **base_stats,
        "spreaker_connected": False,
        "episodes_last_30d": local_last_30d,
        # Legacy field (for compatibility)
        "downloads_last_30d": op3_downloads_30d,
        "plays_last_30d": op3_downloads_30d,
        # Main time period fields (ALWAYS present, even if 0)
        "plays_7d": op3_downloads_7d,
        "plays_30d": op3_downloads_30d,
        "plays_365d": op3_downloads_365d,
        "plays_all_time": op3_downloads_all_time,
        # Top episodes (empty array if none) - ALWAYS return if available
        "top_episodes": op3_top_episodes if op3_top_episodes else [],
        "recent_episode_plays": [],  # Deprecated, use top_episodes
        # Include flag so frontend knows if OP3 data is present
        "op3_enabled": True,  # Always true if we tried to fetch (even if 0)
        # Include error message for debugging (only if we failed to fetch, not if we got 0)
        "op3_error": op3_error_message if op3_error_message and op3_downloads_all_time == 0 else None,
    }
