"""Migration 011: Add Auphonic integration fields to MediaItem model.

Adds fields for tracking Auphonic professional audio processing on uploaded media:
- auphonic_processed: Boolean flag indicating Auphonic processed this file
- auphonic_cleaned_audio_url: GCS URL of Auphonic's cleaned/processed audio
- auphonic_original_audio_url: GCS URL of original audio (kept for failure diagnosis)
- auphonic_output_file: GCS URL of single Auphonic output file (if returned)
- auphonic_metadata: JSON string with show_notes, chapters (if returned separately)

These fields enable tiered transcription routing:
- Pro: Auphonic (transcription + audio processing in one API call)
- Free/Creator/Unlimited: AssemblyAI (transcription only, custom audio processing)
"""

import logging
from sqlalchemy import text
from api.core.database import engine

log = logging.getLogger("migrations.011_add_auphonic_mediaitem_fields")


def run():
    """Add Auphonic integration fields to mediaitem table."""
    
    with engine.connect() as conn:
        # Check if fields already exist (idempotent migration)
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'mediaitem' 
            AND column_name IN (
                'auphonic_processed', 
                'auphonic_cleaned_audio_url', 
                'auphonic_original_audio_url',
                'auphonic_output_file',
                'auphonic_metadata'
            )
        """))
        
        existing_columns = {row[0] for row in result}
        
        if 'auphonic_processed' in existing_columns:
            log.info("[migration_011] auphonic fields already exist on mediaitem, skipping")
            print("Migration 011: Auphonic MediaItem fields already exist, skipping")
            return
        
        log.info("[migration_011] adding auphonic integration fields to mediaitem table")
        print("Migration 011: Adding Auphonic integration fields to MediaItem...")
        
        # Add all five fields
        conn.execute(text("""
            ALTER TABLE mediaitem
            ADD COLUMN IF NOT EXISTS auphonic_processed BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS auphonic_cleaned_audio_url TEXT,
            ADD COLUMN IF NOT EXISTS auphonic_original_audio_url TEXT,
            ADD COLUMN IF NOT EXISTS auphonic_output_file TEXT,
            ADD COLUMN IF NOT EXISTS auphonic_metadata TEXT
        """))
        
        conn.commit()
        
        log.info("[migration_011] auphonic mediaitem fields added successfully")
        print("Migration 011: Auphonic MediaItem fields added successfully")


if __name__ == "__main__":
    run()
