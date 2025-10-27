"""
Migration 031: Add transcription_error field to MediaItem table.

This field stores error messages when transcription fails or detects
instrumental/silence content, providing users with feedback on why
a file might not be ready for assembly.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

def run(db: Session) -> None:
    """Add transcription_error column to mediaitem table."""
    
    # Add the column with default NULL
    db.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'mediaitem' 
                AND column_name = 'transcription_error'
            ) THEN
                ALTER TABLE mediaitem 
                ADD COLUMN transcription_error TEXT DEFAULT NULL;
            END IF;
        END$$;
    """))
    
    db.commit()
    print("✅ Migration 031: Added transcription_error field to mediaitem table")
