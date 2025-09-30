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


def _friendly_name(session: Session, filename: str) -> str:
    media = session.exec(
        select(MediaItem).where(MediaItem.filename == filename)
    ).first()
    if media and getattr(media, "friendly_name", None):
        return str(media.friendly_name)
    return Path(filename).stem or filename


def notify_watchers_processed(filename: str) -> None:
    """Create in-app/email notifications for watchers after transcription."""

    try:
        with Session(db.engine) as session:
            stmt = select(TranscriptionWatch).where(
                TranscriptionWatch.filename == filename,
                TranscriptionWatch.notified_at == None,  # noqa: E711
            )
            watches = session.exec(stmt).all()
            if not watches:
                return

            friendly = _friendly_name(session, filename)

            for watch in watches:
                email = (watch.notify_email or "").strip()
                status = "pending"

                if email:
                    subject = "Your upload is ready to edit"
                    body = (
                        f"Good news! The audio file '{friendly}' has finished processing and is ready in Podcast Plus Plus.\n\n"
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
                    body=f"{friendly} is fully transcribed and ready to use.",
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
            stmt = select(TranscriptionWatch).where(
                TranscriptionWatch.filename == filename,
                TranscriptionWatch.notified_at == None,  # noqa: E711
            )
            watches = session.exec(stmt).all()
            if not watches:
                return

            for watch in watches:
                watch.last_status = f"error:{detail[:120]}"
                session.add(watch)

            session.commit()
    except Exception:  # pragma: no cover - defensive guardrail
        log.warning("[transcribe] failed recording watcher error for %s", filename, exc_info=True)


__all__ = ["notify_watchers_processed", "mark_watchers_failed"]

