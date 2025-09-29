"""Periodic maintenance Celery tasks."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import select

from .app import celery_app
from api.core.database import get_session
from api.core.paths import MEDIA_DIR
from api.models.podcast import Episode, MediaCategory, MediaItem

try:  # pragma: no cover - Python <3.9 fallback
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


@celery_app.task(name="maintenance.purge_expired_uploads")
def purge_expired_uploads() -> dict:
    """Delete expired raw uploads that are no longer referenced."""

    session = next(get_session())
    now = datetime.utcnow()
    removed = 0
    skipped_in_use = 0
    checked = 0

    try:
        query = (
            select(MediaItem)
            .where(MediaItem.category == MediaCategory.main_content)  # type: ignore
            .where(MediaItem.expires_at != None)  # type: ignore
            .where(MediaItem.expires_at <= now)  # type: ignore
            .limit(10_000)
        )
        items = session.exec(query).all()

        episode_query = select(Episode)
        episodes = session.exec(episode_query).all()
        in_use: set[str] = set()
        for ep in episodes:
            for name in (
                getattr(ep, "working_audio_name", None),
                getattr(ep, "final_audio_path", None),
            ):
                if not name:
                    continue
                try:
                    from pathlib import Path

                    in_use.add(Path(str(name)).name)
                except Exception:
                    in_use.add(str(name))

        for media_item in items:
            checked += 1
            filename = getattr(media_item, "filename", None)
            if not filename:
                continue
            if filename in in_use:
                skipped_in_use += 1
                continue

            try:
                path = MEDIA_DIR / filename
                if path.exists():
                    try:
                        path.unlink()
                    except Exception:
                        logging.warning(
                            "[purge] Failed to unlink %s", path, exc_info=True
                        )
                session.delete(media_item)
                removed += 1
            except Exception:
                logging.warning(
                    "[purge] Failed to delete MediaItem %s",
                    getattr(media_item, "id", None),
                    exc_info=True,
                )

        if removed:
            session.commit()
    except Exception:
        session.rollback()
        logging.warning("[purge] purge_expired_uploads failed", exc_info=True)
    finally:
        session.close()

    logging.info(
        "[purge] expired uploads: checked=%s removed=%s skipped_in_use=%s",
        checked,
        removed,
        skipped_in_use,
    )
    return {"checked": checked, "removed": removed, "skipped_in_use": skipped_in_use}
