"""Migration 010: Add Auphonic integration fields to Episode model.

Adds fields for tracking Auphonic professional audio processing:
- auphonic_production_id: UUID from Auphonic API
- auphonic_processed: Boolean flag for tier-based filtering
- auphonic_error: Error message if processing failed

These fields enable tiered audio processing:
- Creator/Pro/Enterprise: Auphonic (professional processing)
- Free/Starter: Current stack (AssemblyAI + clean_engine)
"""

import logging
from sqlalchemy import text
from api.core.database import engine

log = logging.getLogger("migrations.010_add_auphonic_fields")


def run():
    """Add Auphonic integration fields to episode table."""
    
    with engine.connect() as conn:
        # Check if fields already exist (idempotent migration)
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'episode' 
            AND column_name IN ('auphonic_production_id', 'auphonic_processed', 'auphonic_error')
        """))
        
        existing_columns = {row[0] for row in result}
        
        if 'auphonic_production_id' in existing_columns:
            log.info("[migration_010] auphonic fields already exist, skipping")
            print("Migration 010: Auphonic fields already exist, skipping")
            return
        
        log.info("[migration_010] adding auphonic integration fields to episode table")
        print("Migration 010: Adding Auphonic integration fields...")
        
        # Add all three fields in one statement
        conn.execute(text("""
            ALTER TABLE episode
            ADD COLUMN IF NOT EXISTS auphonic_production_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS auphonic_processed BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS auphonic_error TEXT
        """))
        
        conn.commit()
        
        log.info("[migration_010] auphonic fields added successfully")
        print("Migration 010: Auphonic fields added successfully")


if __name__ == "__main__":
    run()
