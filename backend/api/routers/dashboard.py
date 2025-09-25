from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from api.core.auth import get_current_user
from api.core.database import get_session
from api.models.podcast import Episode, EpisodeStatus, Podcast
from api.models.user import User
from api.services.publisher import SpreakerClient

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
    base_stats, local_last_30d = _compute_local_episode_stats(session, current_user.id)

    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        return {
            **base_stats,
            "spreaker_connected": False,
            "episodes_last_30d": local_last_30d,
            "plays_last_30d": None,
            "recent_episode_plays": [],
        }

    client = SpreakerClient(token)
    shows = session.exec(
        select(Podcast)
        .where(Podcast.user_id == current_user.id)
        .where(getattr(Podcast, "spreaker_show_id") != None)  # noqa: E711
    ).all()

    episodes_last_30d = 0
    counted_episode_ids: set[str] = set()
    plays_last_30d = 0
    plays_from_spreaker = False
    episodes_from_spreaker = False
    episodes_by_id: dict[str, dict] = {}

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    date_window = {"from": since.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")}
    stats_params = {**date_window, "group": "day"}
    episodes_params = {"limit": 100, **date_window}

    for show in shows:
        sid = getattr(show, "spreaker_show_id", None)
        if not sid:
            continue
        sid_str = str(sid)

        ok, ep_list = client._get_paginated(
            f"/shows/{sid_str}/episodes",
            params=episodes_params,
            items_key="items",
        )
        if ok and isinstance(ep_list, dict):
            for ep in ep_list.get("items", []):
                episode_id = ep.get("episode_id") or ep.get("id")
                if not episode_id:
                    continue
                episode_id = str(episode_id)
                meta = episodes_by_id.setdefault(episode_id, {"episode_id": episode_id, "show_id": sid_str})
                meta["title"] = ep.get("title") or ep.get("name") or "Untitled"

                pub_dt = _parse_spreaker_datetime(
                    ep.get("published_at")
                    or ep.get("publish_at")
                    or ep.get("auto_published_at")
                )
                if pub_dt:
                    meta["published_at"] = pub_dt
                    if pub_dt <= now and pub_dt >= since and episode_id not in counted_episode_ids:
                        episodes_last_30d += 1
                        counted_episode_ids.add(episode_id)
                        episodes_from_spreaker = True
                else:
                    schedule_dt = _parse_spreaker_datetime(ep.get("publish_at"))
                    if schedule_dt:
                        meta["scheduled_for"] = schedule_dt

        ok, stats = client._get(f"/shows/{sid_str}/statistics/plays", params=stats_params)
        if ok and isinstance(stats, dict):
            buckets = stats.get("items")
            if isinstance(buckets, list):
                for bucket in buckets:
                    plays_val = _coerce_int(bucket.get("plays_count") or bucket.get("plays_total"))
                    if plays_val is not None:
                        plays_last_30d += plays_val
                        plays_from_spreaker = True
            else:
                plays_val = _coerce_int(stats.get("plays_count") or stats.get("plays_total"))
                if plays_val is not None:
                    plays_last_30d += plays_val
                    plays_from_spreaker = True

        ok, ep_stats = client.get_show_episodes_plays_totals(sid_str, params=stats_params)
        if ok and isinstance(ep_stats, dict):
            for item in ep_stats.get("items") or []:
                episode_id = item.get("episode_id") or item.get("id")
                if not episode_id:
                    continue
                episode_id = str(episode_id)
                meta = episodes_by_id.setdefault(episode_id, {"episode_id": episode_id, "show_id": sid_str})
                meta.setdefault("title", item.get("title") or item.get("name") or "Untitled")

                plays_val = None
                for key in ("plays_count", "plays_total", "plays", "count", "play_count"):
                    plays_val = _coerce_int(item.get(key))
                    if plays_val is not None:
                        break
                if plays_val is not None:
                    meta["plays_total"] = meta.get("plays_total", 0) + plays_val

                downloads_val = None
                for key in ("downloads_count", "downloads_total", "downloads"):
                    downloads_val = _coerce_int(item.get(key))
                    if downloads_val is not None:
                        break
                if downloads_val is not None:
                    meta["downloads_total"] = meta.get("downloads_total", 0) + downloads_val

    published_episodes = [
        meta for meta in episodes_by_id.values()
        if meta.get("published_at") and meta["published_at"] <= now
    ]
    published_episodes.sort(key=lambda m: m["published_at"], reverse=True)

    recent_episode_plays = []
    for meta in published_episodes[:3]:
        entry = {
            "episode_id": meta["episode_id"],
            "title": meta.get("title") or "Untitled",
            "plays_total": meta.get("plays_total"),
            "published_at": meta["published_at"].isoformat(),
        }
        if "downloads_total" in meta:
            entry["downloads_total"] = meta["downloads_total"]
        recent_episode_plays.append(entry)

    return {
        **base_stats,
        "spreaker_connected": True,
        "episodes_last_30d": episodes_last_30d if episodes_from_spreaker else local_last_30d,
        "plays_last_30d": plays_last_30d if plays_from_spreaker else None,
        "recent_episode_plays": recent_episode_plays,
    }
