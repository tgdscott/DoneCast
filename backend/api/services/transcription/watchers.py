"""Shared helpers for notifying upload watchers."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from api.core import database as db
from api.models.notification import Notification
from api.models.podcast import MediaItem
from api.models.transcription import TranscriptionWatch
from api.services.mailer import mailer

log = logging.getLogger("transcription.watchers")



def _candidate_filenames(filename: str) -> list[str]:
    """Return potential stored filename variants for a processed upload."""

    raw = (filename or "").strip()
    if not raw:
        return []

    variants: set[str] = set()

    def _record(value: str) -> None:
        if not value:
            return
        trimmed = value.strip()
        if not trimmed:
            return
        variants.add(trimmed)
        normalized = trimmed.replace("\\", "/")
        variants.add(normalized)

        # Remove scheme-specific prefixes and accumulate sub-paths.
        lowered = normalized.lower()
        remainder = normalized
        if "://" in normalized:
            remainder = normalized.split("://", 1)[1]
        elif lowered.startswith("//"):
            remainder = normalized[2:]

        if remainder and remainder != normalized:
            variants.add(remainder)

        # Split host/path style strings into bucket + key pieces.
        path_part = remainder
        if remainder.startswith("storage.googleapis.com/"):
            path_part = remainder[len("storage.googleapis.com/") :]
            if path_part:
                variants.add(path_part)
        if "/" in path_part:
            bucket_part, after = path_part.split("/", 1)
            if bucket_part and after:
                variants.add(f"{bucket_part}/{after}")
                variants.add(after)
                variants.add(f"gs://{bucket_part}/{after}")
            elif after:
                variants.add(after)

        base = Path(normalized).name
        if base:
            variants.add(base)

    # Strip query string / fragment but keep the original for completeness.
    no_query = raw.split("?", 1)[0].split("#", 1)[0]
    _record(raw)
    _record(no_query)

    # Drop empties and preserve insertion order roughly by sorting on length then value.
    cleaned = [v for v in variants if v]
    cleaned.sort(key=lambda v: (len(v), v))
    return cleaned


def _friendly_name(session: Session, filename: str, *, fallback: str | None = None) -> str:

    media = session.exec(
        select(MediaItem).where(MediaItem.filename == filename)
    ).first()
    if media and getattr(media, "friendly_name", None):
        return str(media.friendly_name)

    if fallback:
        return fallback
    return Path(filename).stem or filename


def _load_outstanding_watches(session: Session, filename: str) -> list[TranscriptionWatch]:
    candidates = _candidate_filenames(filename)
    if not candidates:
        return []

    stmt = select(TranscriptionWatch).where(
        TranscriptionWatch.notified_at == None,  # noqa: E711
        TranscriptionWatch.filename.in_(candidates),
    )
    watches = session.exec(stmt).all()

    # Deduplicate by id in case multiple variants matched the same row
    seen: set[str] = set()
    ordered: list[TranscriptionWatch] = []
    for watch in watches:
        key = str(getattr(watch, "id", ""))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(watch)
    return ordered

def notify_watchers_processed(filename: str) -> None:
    """Create in-app/email notifications for watchers after transcription."""

    try:
        with Session(db.engine) as session:

            watches = _load_outstanding_watches(session, filename)
            if not watches:
                return

            friendly = _friendly_name(
                session,
                filename,
                fallback=(watches[0].friendly_name if watches and watches[0].friendly_name else None),
            )


            for watch in watches:
                email = (watch.notify_email or "").strip()
                status = "pending"


                # Normalize stored filename so future lookups succeed even if the
                # original watch used a shorthand variant.
                if (watch.filename or "").strip() != filename:
                    watch.filename = filename

                friendly_text = (watch.friendly_name or friendly or Path(filename).stem or filename)

                if email:
                    subject = "Your recording is ready to edit"
                    # Include download link and 24-hour retention notice
                    body = (
                        f"Good news! Your recording '{friendly_text}' has finished processing and is ready in Podcast Plus Plus.\n\n"
                        
                        f"💾 Download your raw recording (valid for 24 hours):\n"
                        f"https://app.podcastplusplus.com/media-library\n\n"
                        
                        "💡 Tip: Download a backup copy now! The raw file will be automatically deleted after 24 hours.\n\n"
                        
                        "You can return to the dashboard to continue building your episode."
                    )
                    try:
                        sent = mailer.send(email, subject, body)
                        status = "sent" if sent else "email-failed"
                    except Exception:  # pragma: no cover - email best-effort
                        log.warning("[transcribe] mail send failed for %s", filename, exc_info=True)
                        status = "email-error"
                else:
                    status = "no-email"

                note = Notification(
                    user_id=watch.user_id,
                    type="transcription",
                    title="Upload processed",

                    body=f"{friendly_text} is fully transcribed and ready to use.",

                )
                session.add(note)

                watch.notified_at = datetime.utcnow()
                watch.last_status = status
                session.add(watch)

            session.commit()
    except Exception:  # pragma: no cover - defensive guardrail
        log.warning("[transcribe] failed notifying watchers for %s", filename, exc_info=True)


def mark_watchers_failed(filename: str, detail: str) -> None:
    """Record a failure for any outstanding watchers and create error notifications."""

    try:
        with Session(db.engine) as session:

            watches = _load_outstanding_watches(session, filename)

            if not watches:
                return

            for watch in watches:

                if (watch.filename or "").strip() != filename:
                    watch.filename = filename

                watch.last_status = f"error:{detail[:120]}"
                session.add(watch)
                
                # Create error notification for user
                try:
                    friendly = _friendly_name(session, filename, fallback=filename)
                    notification = Notification(
                        user_id=watch.user_id,
                        type="error",
                        title="Transcription Failed",
                        body=f"Failed to transcribe '{friendly}': {detail[:200]}"
                    )
                    session.add(notification)
                    log.info("[transcribe] Created error notification for user %s", watch.user_id)
                except Exception as notif_err:
                    log.warning("[transcribe] Failed to create error notification: %s", notif_err, exc_info=True)

            session.commit()
    except Exception:  # pragma: no cover - defensive guardrail
        log.warning("[transcribe] failed recording watcher error for %s", filename, exc_info=True)


__all__ = ["notify_watchers_processed", "mark_watchers_failed"]

