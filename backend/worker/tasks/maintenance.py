"""Periodic maintenance Celery tasks."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta

from pathlib import Path

from sqlmodel import select

from .app import celery_app
from api.core.database import get_session
from api.core.paths import MEDIA_DIR, FINAL_DIR
from api.models.podcast import Episode, MediaCategory, MediaItem
from infrastructure.gcs import delete_blob

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


@celery_app.task(name="maintenance.purge_published_episode_mirrors")
def purge_published_episode_mirrors() -> dict:
    """Remove mirrored audio for episodes published to Spreaker more than 7 days ago."""

    session = next(get_session())
    cutoff = datetime.utcnow() - timedelta(days=7)
    checked = 0
    removed_local = 0
    removed_remote = 0

    try:
        episodes = session.exec(
            select(Episode).where(Episode.spreaker_episode_id != None)  # type: ignore
        ).all()

        for episode in episodes:
            try:
                meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
                if not isinstance(meta, dict):
                    meta = {}
            except Exception:
                meta = {}

            local_basename = meta.get("mirrored_local_basename")
            if not local_basename:
                continue

            publish_at = getattr(episode, "publish_at", None) or getattr(episode, "processed_at", None)
            if not publish_at or publish_at > cutoff:
                continue

            checked += 1
            local_path = (FINAL_DIR / Path(str(local_basename)).name).resolve()
            if local_path.exists():
                try:
                    local_path.unlink()
                    removed_local += 1
                except Exception:
                    logging.warning("[purge] failed to delete mirrored audio %s", local_path, exc_info=True)

            gcs_uri = meta.get("mirrored_gcs_uri")
            if isinstance(gcs_uri, str) and gcs_uri.startswith("gs://"):
                try:
                    bucket_key = gcs_uri[5:]
                    bucket, _, key = bucket_key.partition("/")
                    if bucket and key:
                        delete_blob(bucket, key)
                        removed_remote += 1
                except Exception:
                    logging.warning("[purge] failed to delete mirrored blob %s", gcs_uri, exc_info=True)

            meta.pop("mirrored_local_basename", None)
            meta.pop("mirrored_gcs_uri", None)
            meta["mirrored_local_removed_at"] = datetime.utcnow().isoformat() + "Z"
            episode.meta_json = json.dumps(meta)
            session.add(episode)

        if removed_local or removed_remote:
            session.commit()
    except Exception:
        session.rollback()
        logging.warning("[purge] purge_published_episode_mirrors failed", exc_info=True)
    finally:
        session.close()

    logging.info(
        "[purge] mirrors: checked=%s removed_local=%s removed_remote=%s",
        checked,
        removed_local,
        removed_remote,
    )
    return {
        "checked": checked,
        "removed_local": removed_local,
        "removed_remote": removed_remote,
    }
