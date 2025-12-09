from __future__ import annotations

import logging
from typing import Any

from api.core.database import session_scope
from api.models.notification import Notification
from api.models.podcast import Episode

log = logging.getLogger(__name__)


def _friendly_episode_title(session: Any, episode_id: Any) -> str:
    """Return a user-friendly episode title without exposing UUIDs."""
    try:
        episode = session.get(Episode, episode_id)
        title = getattr(episode, "title", None) if episode else None
        if title:
            return str(title)
    except Exception:
        log.debug("[notification] Failed to resolve episode title", exc_info=True)
    return "Episode"


def create_final_notification(*, user_id: Any, episode_id: Any) -> None:
    """Persist a completion notification when assembly succeeds."""
    try:
        with session_scope() as session:
            body_title = _friendly_episode_title(session, episode_id)
            note = Notification(
                user_id=user_id,
                type="assembly",
                title="Episode ready",
                body=f"{body_title} is ready",
            )
            session.add(note)
            session.commit()
    except Exception:
        log.warning("[notification] Failed to create final notification", exc_info=True)


def send_episode_failure_alert(episode_id: Any, user_id: Any, error_message: str | None = None) -> None:
    """Emit a notification when assembly fails, avoiding user-facing UUIDs."""
    try:
        with session_scope() as session:
            body_title = _friendly_episode_title(session, episode_id)
            trimmed_error = (error_message or "").strip()
            note_body = f"{body_title} failed to assemble" + (f": {trimmed_error}" if trimmed_error else "")
            note = Notification(
                user_id=user_id,
                type="assembly_error",
                title="Episode failed",
                body=note_body,
            )
            session.add(note)
            session.commit()
    except Exception:
        log.warning("[notification] Failed to emit failure notification", exc_info=True)
