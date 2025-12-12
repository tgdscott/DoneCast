"""
Migration 101: Add audio_processing_threshold_label to user table

Adds a new column to allow users to set a qualitative quality threshold
(e.g., 'fairly_bad') that determines when uploaded audio should be routed
to advanced (Auphonic) processing based on detected quality.

Default: 'fairly_bad' - routes top 2 quality levels (good, slightly_bad) 
to standard processing and bottom 3 to advanced processing.
"""

import logging
from sqlalchemy import text
from api.core.database import engine

log = logging.getLogger(__name__)

def upgrade():
    """Add audio_processing_threshold_label column to user table."""
    log.info("[migration_101] Adding audio_processing_threshold_label column to user table")
    
    with engine.begin() as conn:
        try:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='user' AND column_name='audio_processing_threshold_label'
            """))
            if result.fetchone():
                log.info("[migration_101] Column audio_processing_threshold_label already exists, skipping")
                return
            
            # Add the column with default value
            conn.execute(text("""
                ALTER TABLE "user" 
                ADD COLUMN audio_processing_threshold_label VARCHAR(50) DEFAULT 'very_bad'
            """))
            log.info("[migration_101] Successfully added audio_processing_threshold_label column")
        except Exception as e:
            log.error(f"[migration_101] Failed to add audio_processing_threshold_label column: {e}")
            raise

def downgrade():
    """Remove audio_processing_threshold_label column from user table."""
    log.info("[migration_101] Removing audio_processing_threshold_label column from user table")
    
    with engine.begin() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE "user" 
                DROP COLUMN IF EXISTS audio_processing_threshold_label
            """))
            log.info("[migration_101] Successfully removed audio_processing_threshold_label column")
        except Exception as e:
            log.error(f"[migration_101] Failed to remove audio_processing_threshold_label column: {e}")
            raise
