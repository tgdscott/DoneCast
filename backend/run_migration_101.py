#!/usr/bin/env python3
"""
Run migration 101: Add audio_processing_threshold_label column

This script can be run directly on the production database via Cloud Run Jobs
or executed locally pointing to the production database.
"""

import sys
import os

# Add backend to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
from sqlalchemy import text, inspect
from api.core.database import get_engine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def run_migration():
    """Add audio_processing_threshold_label column to user table."""
    log.info("[migration_101] Starting migration...")
    
    engine = get_engine()
    
    with engine.connect() as conn:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('user')]
        
        if 'audio_processing_threshold_label' in columns:
            log.info("[migration_101] Column audio_processing_threshold_label already exists, skipping")
            return
        
        try:
            # Add the column with default value
            log.info("[migration_101] Adding audio_processing_threshold_label column to user table")
            conn.execute(text("""
                ALTER TABLE "user" 
                ADD COLUMN audio_processing_threshold_label VARCHAR(50) DEFAULT 'very_bad'
            """))
            conn.commit()
            log.info("[migration_101] ✅ Successfully added audio_processing_threshold_label column")
        except Exception as e:
            conn.rollback()
            log.error(f"[migration_101] ❌ Failed to add column: {e}")
            raise

if __name__ == "__main__":
    try:
        run_migration()
        print("✅ Migration completed successfully")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
