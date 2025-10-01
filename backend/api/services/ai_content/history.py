from __future__ import annotations

from typing import List

# Tiny, provider-agnostic history helpers. Keep this file small and without router imports.

from sqlmodel import Session, select
from sqlalchemy import desc, text
from ...models.podcast import Episode, EpisodeSection
from ...core.database import engine


def _clip(s: str, max_len: int = 160) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_len else (s[: max_len - 1] + "…")


def get_recent_titles(podcast_id, n: int = 10) -> List[str]:
    """Latest episode titles for a podcast, newest first.

    Ordered by publish_at DESC then created_at DESC. Truncated to keep prompts small.
    """
    if podcast_id is None or (isinstance(podcast_id, str) and not podcast_id.strip()):
        return []
    try:
        with Session(engine) as session:
            stmt = (
                select(Episode.title)
                .where(Episode.podcast_id == podcast_id)
                .order_by(text("publish_at DESC"), text("created_at DESC"))
                .limit(n)
            )
            rows = list(session.exec(stmt))
            return [_clip((r or "")) for r in rows if (r or "").strip()]
    except Exception:
        # Clear fallback; callers handle empty history gracefully.
        return []


def get_recent_notes(podcast_id, n: int = 10) -> List[str]:
    """Latest episode notes/descriptions for a podcast, newest first.

    Ordered by publish_at DESC then created_at DESC. Truncated.
    """
    if podcast_id is None or (isinstance(podcast_id, str) and not podcast_id.strip()):
        return []
    try:
        with Session(engine) as session:
            stmt = (
                select(Episode.show_notes)
                .where(Episode.podcast_id == podcast_id)
                .order_by(text("publish_at DESC"), text("created_at DESC"))
                .limit(n)
            )
            rows = list(session.exec(stmt))
            return [_clip((r or "")) for r in rows if (r or "").strip()]
    except Exception:
        return []


def get_recent_sections(podcast_id, tag: str, section_type: str, n: int = 10) -> List[str]:
    """Latest section scripts for a podcast/tag/type, newest first.

    Returns list of content strings (trimmed), capped at n.
    """
    if podcast_id is None or (isinstance(podcast_id, str) and not podcast_id.strip()):
        return []
    try:
        with Session(engine) as session:
            stmt = (
                select(EpisodeSection.content)
                .where(EpisodeSection.podcast_id == podcast_id)
                .where(EpisodeSection.tag == tag)
                .where(EpisodeSection.section_type == section_type)
                .order_by(text("created_at DESC"))
                .limit(n)
            )
            rows = list(session.exec(stmt))
            return [_clip((r or ""), 800) for r in rows if (r or "").strip()]
    except Exception:
        return []
