#!/usr/bin/env python3
"""
Run migration 102: Add episode length management fields

This script adds length management fields to PodcastTemplate and User tables.
Can be run directly or will be auto-executed on server startup via one_time_migrations.py
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
    """Add episode length management fields to podcasttemplate and user tables."""
    log.info("[migration_102] Starting episode length management migration...")
    
    engine = get_engine()
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # Check PodcastTemplate table
        template_cols = [col['name'] for col in inspector.get_columns('podcasttemplate')]
        user_cols = [col['name'] for col in inspector.get_columns('user')]
        
        # Add template columns if missing
        template_fields_needed = [
            'soft_min_length_seconds',
            'soft_max_length_seconds',
            'hard_min_length_seconds',
            'hard_max_length_seconds',
            'length_management_enabled'
        ]
        
        missing_template_fields = [f for f in template_fields_needed if f not in template_cols]
        
        if missing_template_fields:
            try:
                log.info("[migration_102] Adding %d fields to podcasttemplate table", len(missing_template_fields))
                conn.execute(text("""
                    ALTER TABLE podcasttemplate
                    ADD COLUMN IF NOT EXISTS soft_min_length_seconds INTEGER,
                    ADD COLUMN IF NOT EXISTS soft_max_length_seconds INTEGER,
                    ADD COLUMN IF NOT EXISTS hard_min_length_seconds INTEGER,
                    ADD COLUMN IF NOT EXISTS hard_max_length_seconds INTEGER,
                    ADD COLUMN IF NOT EXISTS length_management_enabled BOOLEAN DEFAULT FALSE NOT NULL;
                """))
                conn.commit()
                log.info("[migration_102] ✅ Added length management fields to podcasttemplate")
            except Exception as e:
                conn.rollback()
                log.error(f"[migration_102] ❌ Failed to add podcasttemplate fields: {e}")
                raise
        else:
            log.info("[migration_102] PodcastTemplate fields already exist, skipping")
        
        # Add user columns if missing
        user_fields_needed = ['speed_up_factor', 'slow_down_factor']
        missing_user_fields = [f for f in user_fields_needed if f not in user_cols]
        
        if missing_user_fields:
            try:
                log.info("[migration_102] Adding %d fields to user table", len(missing_user_fields))
                conn.execute(text("""
                    ALTER TABLE "user"
                    ADD COLUMN IF NOT EXISTS speed_up_factor DOUBLE PRECISION DEFAULT 1.05 NOT NULL,
                    ADD COLUMN IF NOT EXISTS slow_down_factor DOUBLE PRECISION DEFAULT 0.95 NOT NULL;
                """))
                conn.commit()
                log.info("[migration_102] ✅ Added speed adjustment fields to user table")
            except Exception as e:
                conn.rollback()
                log.error(f"[migration_102] ❌ Failed to add user fields: {e}")
                raise
        else:
            log.info("[migration_102] User speed adjustment fields already exist, skipping")
        
        # Add constraints if not exists
        try:
            log.info("[migration_102] Adding range constraints to user speed factors")
            # Check if constraints already exist
            constraints = inspector.get_check_constraints('user')
            constraint_names = [c['name'] for c in constraints]
            
            if 'check_speed_up_factor_range' not in constraint_names:
                conn.execute(text("""
                    ALTER TABLE "user"
                    ADD CONSTRAINT check_speed_up_factor_range 
                    CHECK (speed_up_factor >= 1.0 AND speed_up_factor <= 1.25);
                """))
                log.info("[migration_102] ✅ Added speed_up_factor constraint")
            
            if 'check_slow_down_factor_range' not in constraint_names:
                conn.execute(text("""
                    ALTER TABLE "user"
                    ADD CONSTRAINT check_slow_down_factor_range 
                    CHECK (slow_down_factor >= 0.75 AND slow_down_factor < 1.0);
                """))
                log.info("[migration_102] ✅ Added slow_down_factor constraint")
            
            conn.commit()
        except Exception as e:
            # Constraints might fail if data already violates them, don't fail the whole migration
            log.warning(f"[migration_102] ⚠️ Could not add constraints (non-critical): {e}")

if __name__ == "__main__":
    try:
        run_migration()
        print("✅ Migration 102 completed successfully")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Migration 102 failed: {e}")
        sys.exit(1)
