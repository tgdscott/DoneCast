"""
Migration 040: Add advanced audio processing preference to the user table.

This creates a persisted toggle that determines whether an account uses the
advanced mastering pipeline or the standard AssemblyAI flow.
"""

import logging

from sqlalchemy import inspect, text
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add the use_advanced_audio_processing flag to the user table."""

    log.info("[migration_040] Starting advanced audio preference migration")

    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        columns = {col["name"]: col for col in inspector.get_columns("user")}

        if "use_advanced_audio_processing" not in columns:
            log.info("[migration_040] Adding use_advanced_audio_processing column to user table")
            session.execute(
                text(
                    """
                    ALTER TABLE "user"
                    ADD COLUMN use_advanced_audio_processing BOOLEAN NOT NULL DEFAULT FALSE
                    """
                )
            )
            log.info("[migration_040] ✅ Column added")
        else:
            log.info("[migration_040] Column already exists, skipping")

        session.commit()
        log.info("[migration_040] ✅ Migration completed successfully")
    except Exception as exc:
        log.error("[migration_040] ❌ Migration failed: %s", exc, exc_info=True)
        session.rollback()
        raise

