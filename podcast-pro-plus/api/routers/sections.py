from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from uuid import UUID
from sqlmodel import Session, select

# Use the same auth dependency style as other routers
from api.core.auth import get_current_user
from api.core.database import get_session
from api.models.user import User
from api.models.podcast import (
    Episode,
    EpisodeSection,
    SectionType,
    EpisodeStatus,
)
from api.services.ai_content.schemas import SuggestSectionIn, SuggestSectionOut
from api.services.ai_content.generators.section import suggest_section

router = APIRouter(prefix="/sections", tags=["sections"])


def _count_podcast_episodes(session: Session, podcast_id: UUID, user_id: UUID) -> int:
    """Count processed (built) episodes for this podcast & user."""
    try:
        from sqlalchemy import func
        q = select(func.count(Episode.id)).where(Episode.user_id == user_id, Episode.podcast_id == podcast_id)
        try:
            q = q.where(Episode.status == EpisodeStatus.processed)
        except Exception:
            q = q.where(Episode.status == "processed")
        return session.exec(q).one()
    except Exception:
        return 0


@router.get("/tags")
def list_section_tags(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return up to 4 distinct tags used by this user for this podcast,
    along with the section types they've been used with.
    """
    stmt = (
        select(EpisodeSection.tag, EpisodeSection.section_type)
        .where(EpisodeSection.user_id == current_user.id)
        .where(EpisodeSection.podcast_id == podcast_id)
    )
    rows = list(session.exec(stmt))
    tags: Dict[str, set] = {}
    for t, st in rows:
        # t is the tag string, st is the SectionType (enum or string)
        tags.setdefault(str(t), set()).add(str(st))

    items = [{"tag": k, "types": sorted(list(v))} for k, v in tags.items()]
    items.sort(key=lambda x: x["tag"].lower())
    return {"tags": items[:4]}


@router.post("/save", status_code=201)
def save_section(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Persist a section row. Enforce <= 4 distinct tags per podcast/user.
    """
    tag = (payload.get("tag") or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="tag is required")

    section_type_raw = str(payload.get("section_type") or "intro").lower()
    if section_type_raw not in {"intro", "outro", "custom"}:
        raise HTTPException(status_code=400, detail="invalid section_type")

    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    podcast_id = payload.get("podcast_id")
    if not podcast_id:
        raise HTTPException(status_code=400, detail="podcast_id is required")

    episode_id = payload.get("episode_id")
    voice_id = payload.get("voice_id")
    voice_name = payload.get("voice_name")

    # Enforce at most 4 distinct tags per podcast/user (robust to tuple/scalar results)
    rows = session.exec(
        select(EpisodeSection.tag)
        .where(EpisodeSection.user_id == current_user.id)
        .where(EpisodeSection.podcast_id == podcast_id)
        .distinct()
    ).all()
    distinct_tags = sorted(
        {
            (r[0] if isinstance(r, tuple) else r)
            for r in rows
            if (r is not None)
        }
    )
    if tag not in distinct_tags and len(distinct_tags) >= 4:
        raise HTTPException(status_code=409, detail="MAX_TAGS_REACHED")

    rec = EpisodeSection(
        user_id=current_user.id,
        podcast_id=UUID(str(podcast_id)),
        episode_id=UUID(str(episode_id)) if episode_id else None,
        tag=tag,
        section_type=SectionType(section_type_raw),
    source_type=EpisodeSection.SectionSourceType.tts,  # use the model's inner enum
        content=content,
        voice_id=voice_id,
        voice_name=voice_name,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return {"id": str(rec.id)}


@router.post("/suggest", response_model=SuggestSectionOut)
def ai_suggest_section(
    inp: SuggestSectionIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SuggestSectionOut:
    # Gate: require at least 5 episodes for this podcast before suggestions
    try:
        pid = UUID(str(inp.podcast_id))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid podcast_id")

    if _count_podcast_episodes(session, pid, current_user.id) < 5:
        raise HTTPException(status_code=403, detail="NOT_ENOUGH_HISTORY")

    # Limit lookback to last 10 by design (cap regardless of client input)
    inp.history_count = min(int(getattr(inp, "history_count", 10) or 10), 10)

    # Attach transcript if missing using existing discovery logic from ai_suggestions router
    if not getattr(inp, "transcript_path", None):
        try:
            from . import ai_suggestions as _ai
            inp.transcript_path = (
                _ai._discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, "hint", None))
                or _ai._discover_or_materialize_transcript(str(inp.episode_id))
            )
        except Exception:
            inp.transcript_path = None

    return suggest_section(inp)
