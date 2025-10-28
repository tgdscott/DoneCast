from __future__ import annotations

from typing import Optional, Any, Dict, List, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlmodel import select

from api.models.podcast import Episode, Podcast, PodcastTemplate


def get_episode_by_id(session: Session, episode_id: UUID, user_id: Optional[UUID] = None) -> Optional[Episode]:
    q = select(Episode).where(Episode.id == episode_id)
    if user_id is not None:
        q = q.where(Episode.user_id == user_id)
    return session.exec(q).first()


def get_podcast_by_id(session: Session, podcast_id: UUID) -> Optional[Podcast]:
    return session.exec(select(Podcast).where(Podcast.id == podcast_id)).first()


def get_template_by_id(session: Session, template_id: UUID) -> Optional[PodcastTemplate]:
    return session.exec(select(PodcastTemplate).where(PodcastTemplate.id == template_id)).first()


def get_first_podcast_for_user(session: Session, user_id: Any) -> Optional[Podcast]:
    return session.exec(select(Podcast).where(Podcast.user_id == user_id)).first()


def create_episode(session: Session, data: Dict[str, Any]) -> Episode:
    ep = Episode(**data)
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return ep


def update_episode(session: Session, ep: Episode, fields: Dict[str, Any]) -> Episode:
    for k, v in fields.items():
        setattr(ep, k, v)
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return ep


def delete_episode(session: Session, ep: Episode) -> None:
    """Delete episode and all related child records.
    
    Manually cascades deletions to avoid foreign key constraint violations.
    Child records: MediaItem.used_in_episode_id, UsageRecord.
    """
    from api.models.podcast import MediaItem
    from api.models.usage import UsageRecord
    
    episode_id = ep.id
    
    # Clear MediaItem.used_in_episode_id references (don't delete the media itself)
    media_items = session.exec(
        select(MediaItem).where(MediaItem.used_in_episode_id == episode_id)
    ).all()
    for item in media_items:
        item.used_in_episode_id = None
        session.add(item)
    
    # Delete UsageRecord entries for this episode
    usage_records = session.exec(
        select(UsageRecord).where(UsageRecord.episode_id == episode_id)
    ).all()
    for record in usage_records:
        session.delete(record)
    
    # Finally delete the episode itself
    session.delete(ep)
    session.commit()


def episode_exists_with_number(session: Session, podcast_id, season_number: int, episode_number: int, exclude_id: Optional[UUID] = None) -> bool:
    cand = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast_id, Episode.season_number == season_number, Episode.episode_number == episode_number)
    ).first()
    if not cand:
        return False
    if exclude_id and getattr(cand, 'id', None) == exclude_id:
        return False
    return True
