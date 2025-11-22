"""
Migration 044: Add use_auphonic flag to MediaItem table.

This flag is the sole source of truth for transcription routing:
- use_auphonic=True → Auphonic transcription
- use_auphonic=False/None → AssemblyAI transcription

Set by checkbox when file is uploaded. No fallbacks - failures fail loudly.
"""

import logging

from sqlalchemy import inspect, text
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add the use_auphonic flag to the mediaitem table."""

    log.info("[migration_044] Starting MediaItem.use_auphonic migration")

    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        # SQLModel creates table name as lowercase 'mediaitem' (not 'media_item')
        columns = {col["name"]: col for col in inspector.get_columns("mediaitem")}

        if "use_auphonic" not in columns:
            log.info("[migration_044] Adding use_auphonic column to mediaitem table")
            session.execute(
                text(
                    """
                    ALTER TABLE mediaitem
                    ADD COLUMN use_auphonic BOOLEAN NOT NULL DEFAULT FALSE
                    """
                )
            )
            log.info("[migration_044] ✅ Column added")
        else:
            log.info("[migration_044] Column already exists, skipping")

        session.commit()
        log.info("[migration_044] ✅ Migration completed successfully")
    except Exception as exc:
        log.error("[migration_044] ❌ Migration failed: %s", exc, exc_info=True)
        session.rollback()
        raise

