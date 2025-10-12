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
from api.services.op3_analytics import OP3Analytics

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
async def dashboard_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard statistics from local database and OP3 analytics.
    
    This endpoint now uses OP3 (Open Podcast Prefix Project) for download/play stats
    instead of Spreaker, as we're migrating away from Spreaker.
    """
    try:
        base_stats, local_last_30d = _compute_local_episode_stats(session, current_user.id)
    except Exception:
        # If local aggregation fails, degrade gracefully
        base_stats, local_last_30d = ({
            "total_episodes": 0,
            "upcoming_scheduled": 0,
            "last_published_at": None,
            "last_assembly_status": None,
        }, 0)

    # Get all podcasts for this user
    try:
        podcasts = session.exec(
            select(Podcast).where(Podcast.user_id == current_user.id)
        ).all()
    except Exception:
        podcasts = []
    
    if not podcasts:
        return {
            **base_stats,
            "spreaker_connected": False,
            "episodes_last_30d": local_last_30d,
            "plays_last_30d": None,
            "downloads_last_30d": None,
            "recent_episode_plays": [],
        }

    # Fetch download statistics from OP3 for all podcasts
    from api.core.config import settings
    from infrastructure.gcs import get_public_audio_url
    
    total_downloads_30d = 0
    recent_episode_data = []
    op3_client = OP3Analytics()
    
    try:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=30)
        
        # For each podcast, get OP3 stats
        for podcast in podcasts:
            try:
                # Construct RSS feed URL for this podcast  
                # Use the same pattern as the analytics.py endpoint
                if hasattr(podcast, 'feed_url') and podcast.feed_url:
                    rss_url = podcast.feed_url
                else:
                    identifier = getattr(podcast, 'slug', None) or str(podcast.id)
                    base_url = settings.APP_BASE_URL or "https://api.podcastplusplus.com"
                    rss_url = f"{base_url}/v1/rss/{identifier}/feed.xml"
                
                # Fetch show-level stats from OP3
                try:
                    show_stats = await op3_client.get_show_downloads(
                        show_url=rss_url,
                        start_date=since,
                        end_date=now
                    )
                    total_downloads_30d += show_stats.total_downloads
                    logger.info(f"OP3 stats for {podcast.name}: {show_stats.total_downloads} downloads")
                except Exception as e:
                    logger.warning(f"Failed to fetch OP3 stats for podcast {podcast.id}: {e}")
                    continue
                
                # Get recent published episodes for this podcast
                stmt = (
                    select(Episode)
                    .where(Episode.podcast_id == podcast.id)
                    .where(Episode.status == EpisodeStatus.published)
                    .where(Episode.gcs_audio_path.is_not(None))
                    .where(Episode.publish_at.is_not(None))
                    .where(Episode.publish_at >= since)
                    .order_by(Episode.publish_at.desc())
                    .limit(10)
                )
                episodes = session.exec(stmt).all()
                
                # Fetch episode-level stats from OP3
                for episode in episodes:
                    if not episode.gcs_audio_path:
                        continue
                    
                    try:
                        audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)
                        if not audio_url:
                            continue
                        
                        op3_url = f"https://op3.dev/e/{audio_url}"
                        
                        ep_stats = await op3_client.get_episode_downloads(
                            episode_url=op3_url,
                            start_date=since,
                            end_date=now
                        )
                        
                        recent_episode_data.append({
                            "episode_id": str(episode.id),
                            "title": episode.title or "Untitled",
                            "downloads_30d": ep_stats.downloads_30d,
                            "downloads_total": ep_stats.downloads_total,
                            "published_at": episode.publish_at.isoformat() if episode.publish_at else None,
                        })
                    except Exception as e:
                        logger.warning(f"Failed to fetch OP3 stats for episode {episode.id}: {e}")
                        continue
                
            except Exception as e:
                logger.warning(f"Error processing podcast {podcast.id} for OP3 stats: {e}")
                continue
        
        # Sort by downloads and take top 3
        recent_episode_data.sort(key=lambda x: x.get("downloads_30d", 0), reverse=True)
        recent_episode_plays = recent_episode_data[:3]
        
    except Exception as e:
        logger.error(f"Error fetching OP3 dashboard stats: {e}")
        total_downloads_30d = 0
        recent_episode_plays = []
    finally:
        await op3_client.close()

    return {
        **base_stats,
        "spreaker_connected": False,  # We're migrating away from Spreaker
        "episodes_last_30d": local_last_30d,
        "downloads_last_30d": total_downloads_30d,
        "plays_last_30d": total_downloads_30d,  # OP3 tracks downloads, which are equivalent to plays
        "recent_episode_plays": recent_episode_plays,
    }
