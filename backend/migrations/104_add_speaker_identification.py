"""
Migration 104: Add Speaker Identification Settings

Adds speaker identification fields to the Podcast table to enable
speaker labeling in transcripts via voice intro matching.

Fields:
- has_guests: Boolean flag indicating if podcast features guest speakers
- speaker_intros: JSON field storing host voice intro metadata
  Format: {"hosts": [{"name": "Scott", "gcs_path": "gs://...", "order": 0}]}
- guest_library: JSON field storing reusable guest library
  Format: [{"id": "uuid", "name": "Guest Name", "gcs_path": "gs://...", "last_used": "iso-date"}]
"""

from sqlalchemy import text
from sqlmodel import Session


def migrate(session: Session) -> None:
    """Add speaker identification fields to podcast table."""
    
    # Add speaker identification fields to podcast table
    session.exec(text("""
        ALTER TABLE podcast
        ADD COLUMN IF NOT EXISTS has_guests BOOLEAN DEFAULT FALSE NOT NULL,
        ADD COLUMN IF NOT EXISTS speaker_intros JSONB,
        ADD COLUMN IF NOT EXISTS guest_library JSONB;
    """))
    
    session.commit()
    print("✅ Migration 104: Added speaker identification fields")


def rollback(session: Session) -> None:
    """Remove speaker identification fields."""
    
    # Drop columns from podcast table
    session.exec(text("""
        ALTER TABLE podcast
        DROP COLUMN IF EXISTS has_guests,
        DROP COLUMN IF EXISTS speaker_intros,
        DROP COLUMN IF EXISTS guest_library;
    """))
    
    session.commit()
    print("✅ Migration 104 rollback: Removed speaker identification fields")
