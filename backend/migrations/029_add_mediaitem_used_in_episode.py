"""Migration 029: Add used_in_episode_id to MediaItem for raw file cleanup notifications.

Adds tracking for which episode consumed a raw audio file so the system can:
1. Create "safe to delete" notifications when auto-delete is disabled
2. Display badges in Media Library UI showing which files have been used
3. Allow users to confidently clean up raw files after successful episode assembly

This field works with the audio cleanup settings to provide either:
- Auto-delete: Immediate removal after episode assembly (existing behavior)
- Manual delete: Notification + UI badge for user-controlled cleanup (new feature)
"""

import logging
from sqlalchemy import text
from api.core.database import engine

log = logging.getLogger("migrations.029_add_mediaitem_used_in_episode")


def run():
    """Add used_in_episode_id foreign key to mediaitem table."""
    
    with engine.connect() as conn:
        # Check if field already exists (idempotent migration)
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'mediaitem' 
            AND column_name = 'used_in_episode_id'
        """))
        
        existing_column = result.fetchone()
        
        if existing_column:
            log.info("[migration_029] used_in_episode_id already exists on mediaitem, skipping")
            print("Migration 029: used_in_episode_id field already exists, skipping")
            return
        
        log.info("[migration_029] adding used_in_episode_id to mediaitem table")
        print("Migration 029: Adding used_in_episode_id to MediaItem...")
        
        # Add the foreign key field (nullable, since not all files will be used in episodes)
        conn.execute(text("""
            ALTER TABLE mediaitem
            ADD COLUMN IF NOT EXISTS used_in_episode_id UUID REFERENCES episode(id)
        """))
        
        conn.commit()
        
        log.info("[migration_029] ✅ Successfully added used_in_episode_id field")
        print("Migration 029: ✅ Complete - MediaItem now tracks episode usage for cleanup notifications")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
