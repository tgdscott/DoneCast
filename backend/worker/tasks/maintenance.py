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
    """Delete expired raw uploads that are no longer referenced.
    
    For recordings (main_content), enforces 24-hour minimum retention period
    even if used in an episode, giving users time to download a backup.
    """

    session = next(get_session())
    now = datetime.utcnow()
    removed = 0
    skipped_in_use = 0
    skipped_too_young = 0
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
        
        # Only mark files as "in use" if they're referenced by episodes that are NOT complete
        # Complete = processed, published, or scheduled (scheduled not in enum but might exist in DB)
        # We want to KEEP files if ANY episode is: pending, processing, or error
        from api.models.podcast import EpisodeStatus
        
        incomplete_statuses = {
            EpisodeStatus.pending,
            EpisodeStatus.processing,
            EpisodeStatus.error,
        }
        
        for ep in episodes:
            # Check if episode is incomplete (needs the file)
            ep_status = getattr(ep, "status", None)
            if ep_status not in incomplete_statuses:
                # Episode is complete (processed/published), file can be cleaned up
                continue
                
            # Episode is incomplete, keep its files
            # Check direct episode fields
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
            
            # Also check meta_json for main_content_filename (used by retry logic)
            try:
                meta_str = getattr(ep, "meta_json", None)
                if meta_str:
                    meta = json.loads(meta_str)
                    if isinstance(meta, dict):
                        main_content = meta.get("main_content_filename")
                        if main_content:
                            try:
                                in_use.add(Path(str(main_content)).name)
                            except Exception:
                                in_use.add(str(main_content))
            except Exception:
                pass  # Ignore JSON parse errors

        for media_item in items:
            checked += 1
            filename = getattr(media_item, "filename", None)
            if not filename:
                continue
            
            # Enforce 24-hour minimum retention for recordings (gives users "oops" time to download backup)
            created_at = getattr(media_item, "created_at", None)
            if created_at:
                age_hours = (now - created_at).total_seconds() / 3600
                if age_hours < 24:
                    skipped_too_young += 1
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
        "[purge] expired uploads: checked=%s removed=%s skipped_in_use=%s skipped_too_young=%s",
        checked,
        removed,
        skipped_in_use,
        skipped_too_young,
    )
    return {
        "checked": checked, 
        "removed": removed, 
        "skipped_in_use": skipped_in_use,
        "skipped_too_young": skipped_too_young
    }


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
