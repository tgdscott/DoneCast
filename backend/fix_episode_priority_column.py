#!/usr/bin/env python3
"""Quick fix script to add episode.priority column if it's missing.

This script can be run manually to add the priority column if the migration
hasn't run yet or if there was an issue with the migration.

Usage:
    python backend/fix_episode_priority_column.py
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def fix_episode_priority_column():
    """Add priority column to episode table if it doesn't exist."""
    from sqlalchemy import text, inspect
    from api.core.database import engine
    import logging
    
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)
    
    log.info("Checking if episode.priority column exists...")
    
    try:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('episode')]
        
        if 'priority' in columns:
            log.info("✅ episode.priority column already exists!")
            return True
        
        log.info("⚠️  episode.priority column is missing. Adding it now...")
        
        with engine.begin() as conn:
            # Add priority column with default value of 1 (lowest priority)
            conn.execute(text("""
                ALTER TABLE episode 
                ADD COLUMN priority INTEGER NOT NULL DEFAULT 1;
            """))
            
            # Create index on priority for efficient queue ordering queries
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_episode_priority ON episode (priority);
            """))
        
        log.info("✅ Successfully added episode.priority column and index!")
        return True
        
    except Exception as e:
        log.error(f"❌ Failed to add episode.priority column: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = fix_episode_priority_column()
    sys.exit(0 if success else 1)










