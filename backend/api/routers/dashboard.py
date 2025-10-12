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
    op3_show_stats = None
    
    try:
        # Get user's primary podcast RSS feed URL
        # Most users have one podcast, just grab the first one
        podcasts = session.exec(
            select(Podcast).where(Podcast.user_id == current_user.id).limit(1)
        ).all()
        
        podcast = podcasts[0] if podcasts else None
        
        if podcast and podcast.rss_feed_url:
            logger.info(f"Fetching OP3 stats for RSS feed: {podcast.rss_feed_url}")
            
            # Use sync wrapper to fetch OP3 stats (handles async internally)
            op3_show_stats = get_show_stats_sync(podcast.rss_feed_url, days=30)
            
            if op3_show_stats:
                op3_downloads_30d = op3_show_stats.total_downloads
                logger.info(f"OP3 stats retrieved: {op3_downloads_30d} downloads in last 30 days")
            else:
                logger.warning("OP3 stats fetch returned None - may be no data or API error")
        else:
            logger.info("No RSS feed URL available for OP3 stats - using local counts only")
            
    except Exception as e:
        # OP3 fetch failed - log but don't crash dashboard
        logger.error(f"Failed to fetch OP3 analytics: {e}", exc_info=True)
        logger.info("Falling back to local episode counts")
    
    # Build response with OP3 data if available, else local counts
    return {
        **base_stats,
        "spreaker_connected": False,
        "episodes_last_30d": local_last_30d,
        # Use OP3 downloads if available, else None (frontend will handle display)
        "downloads_last_30d": op3_downloads_30d,
        # Legacy field - OP3 provides downloads, not "plays"
        "plays_last_30d": op3_downloads_30d,
        "recent_episode_plays": [],
        # Include flag so frontend knows if OP3 data is present
        "op3_enabled": op3_downloads_30d is not None,
    }
