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

    # Normalize path separators and whitespace
    normalized = raw.replace("\\", "/")
    variants.add(raw)
    variants.add(normalized)

    # gs://bucket/key -> add key and bucket/key variants
    if normalized.startswith("gs://"):
        without_scheme = normalized[len("gs://") :]
        if without_scheme:
            variants.add(without_scheme)
            bucket_split = without_scheme.split("/", 1)
            if len(bucket_split) == 2 and bucket_split[1]:
                variants.add(bucket_split[1])

    # Basename without path components
    base = Path(normalized).name
    if base:
        variants.add(base)

    # Drop empties and preserve insertion order roughly by sorting on length then value
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
                    subject = "Your upload is ready to edit"
                    body = (
                        f"Good news! The audio file '{friendly_text}' has finished processing and is ready in Podcast Plus Plus.\n\n"

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
    """Record a failure for any outstanding watchers."""

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

            session.commit()
    except Exception:  # pragma: no cover - defensive guardrail
        log.warning("[transcribe] failed recording watcher error for %s", filename, exc_info=True)


__all__ = ["notify_watchers_processed", "mark_watchers_failed"]

