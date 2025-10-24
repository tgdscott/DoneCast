from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

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
    now = datetime.utcnow()

    total_episodes = session.exec(
        select(func.count(Episode.id)).where(Episode.user_id == user_id)
    ).one()

    upcoming_scheduled = session.exec(
        select(func.count(Episode.id)).where(
            Episode.user_id == user_id,
            Episode.publish_at != None,  # noqa: E711
            Episode.publish_at > now,
        )
    ).one()

    last_episode = session.exec(
        select(Episode)
        .where(Episode.user_id == user_id)
        .order_by(
            Episode.publish_at.is_(None),
            Episode.publish_at.desc(),
            Episode.created_at.desc(),
        )
        .limit(1)
    ).first()

    last_published_at = None
    last_status = None
    if last_episode:
        ts = getattr(last_episode, "publish_at", None) or getattr(last_episode, "processed_at", None)
        if ts:
            last_published_at = ts.isoformat()
        status_val = getattr(last_episode, "status", None)
        if isinstance(status_val, EpisodeStatus):
            last_status = status_val.value
        elif status_val is not None:
            last_status = str(status_val)

    since = now - timedelta(days=30)
    episodes_last_30d = session.exec(
        select(func.count(Episode.id)).where(
            Episode.user_id == user_id,
            Episode.publish_at != None,  # noqa: E711
            Episode.publish_at >= since,
            Episode.publish_at <= now,  # Only count PAST episodes, not future scheduled ones
        )
    ).one()

    base = {
        "total_episodes": int(total_episodes or 0),
        "upcoming_scheduled": int(upcoming_scheduled or 0),
        "last_published_at": last_published_at,
        "last_assembly_status": last_status,
    }
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
            logger.info(f"Fetching OP3 stats for RSS feed: {rss_url}")
            
            # Use sync wrapper to fetch OP3 stats (handles async internally)
            op3_show_stats = get_show_stats_sync(rss_url, days=30)
            
            if op3_show_stats:
                op3_downloads_7d = op3_show_stats.downloads_7d
                op3_downloads_30d = op3_show_stats.downloads_30d
                op3_downloads_365d = op3_show_stats.downloads_365d
                op3_downloads_all_time = op3_show_stats.downloads_all_time
                op3_top_episodes = op3_show_stats.top_episodes[:3]  # Top 3
                
                if op3_downloads_30d > 0:
                    logger.info(f"OP3 stats SUCCESS: 7d={op3_downloads_7d}, 30d={op3_downloads_30d}, all-time={op3_downloads_all_time}")
                else:
                    logger.warning(f"OP3 returned 0 downloads for {rss_url}")
                    op3_error_message = "OP3 API returned no download data"
            else:
                logger.warning("OP3 stats fetch returned None")
                op3_error_message = "OP3 API returned no data"
            
            # FALLBACK: If self-hosted OP3 has no data yet, use historical TSV
            if (op3_downloads_30d == 0 or op3_downloads_30d is None) and op3_downloads_all_time == 0:
                logger.info("Self-hosted OP3 has no data - falling back to historical TSV")
                historical = get_historical_data()
                op3_downloads_7d = historical.get_total_downloads(days=7)
                op3_downloads_30d = historical.get_total_downloads(days=30)
                op3_downloads_365d = 0  # TSV doesn't have 365-day data
                op3_downloads_all_time = historical.get_total_downloads()
                
                # Get top 3 episodes from historical data
                top_historical = historical.get_top_episodes(limit=3, days=None)  # All-time top episodes
                op3_top_episodes = [
                    {
                        'title': ep['episode_title'],
                        'downloads': ep['downloads']
                    }
                    for ep in top_historical
                ]
                
                if op3_downloads_all_time > 0:
                    logger.info(f"Historical fallback: 7d={op3_downloads_7d}, 30d={op3_downloads_30d}, all-time={op3_downloads_all_time}, top_episodes={len(op3_top_episodes)}")
                    op3_error_message = None  # Clear error since we have historical data
            
    except Exception as e:
        # OP3 fetch failed - log but don't crash dashboard
        logger.error(f"Failed to fetch OP3 analytics: {e}", exc_info=True)
        op3_error_message = f"API error: {str(e)}"
        logger.info("Falling back to local episode counts")
    
    # Include all available time periods (no "smart filtering" - show what we have)
    time_periods = {}
    if op3_downloads_7d is not None:
        time_periods["plays_7d"] = op3_downloads_7d
    if op3_downloads_30d is not None:
        time_periods["plays_30d"] = op3_downloads_30d
    if op3_downloads_365d is not None and op3_downloads_365d > 0:
        time_periods["plays_365d"] = op3_downloads_365d
    if op3_downloads_all_time is not None and op3_downloads_all_time > 0:
        time_periods["plays_all_time"] = op3_downloads_all_time
    
    # Debug logging to diagnose missing stats
    logger.info(f"[DASHBOARD] OP3 Stats - 7d: {op3_downloads_7d}, 30d: {op3_downloads_30d}, 365d: {op3_downloads_365d}, all-time: {op3_downloads_all_time}")
    logger.info(f"[DASHBOARD] Time periods dict: {time_periods}")
    logger.info(f"[DASHBOARD] Top episodes count: {len(op3_top_episodes)}")
    
    # Build response with OP3 data if available, else local counts
    return {
        **base_stats,
        "spreaker_connected": False,
        "episodes_last_30d": local_last_30d,
        # Use OP3 downloads if available, else None (frontend will handle display)
        "downloads_last_30d": op3_downloads_30d,
        # Legacy field - OP3 provides downloads, not "plays"
        "plays_last_30d": op3_downloads_30d,
        # New multi-period fields (with smart filtering applied)
        **time_periods,
        # Top episodes
        "top_episodes": op3_top_episodes,
        "recent_episode_plays": [],  # Deprecated, use top_episodes
        # Include flag so frontend knows if OP3 data is present
        "op3_enabled": op3_downloads_30d is not None,
        # Include error message for debugging (not shown to user)
        "op3_error": op3_error_message if op3_downloads_30d is None else None,
    }
