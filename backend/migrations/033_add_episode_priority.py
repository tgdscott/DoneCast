"""
Migration 033: Add priority column to episode table for queue ordering.

Adds priority field to episode table to support tier-based queue priority.
Priority values: Starter=1, Creator=2, Pro=3, Executive=4, Enterprise=5, Unlimited=6

PostgreSQL ONLY.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add priority column to episode table (PostgreSQL ONLY)"""
    
    log.info("[migration_033] Starting episode priority column migration (PostgreSQL)...")
    
    try:
        # Check if column already exists
        bind = session.get_bind()
        inspector = inspect(bind)
        columns = [col['name'] for col in inspector.get_columns('episode')]
        
        if 'priority' in columns:
            log.info("[migration_033] Priority column already exists, skipping...")
            return
        
        # Add priority column with default value of 1 (lowest priority)
        log.info("[migration_033] Adding priority column to episode table...")
        session.execute(text("""
            ALTER TABLE episode 
            ADD COLUMN priority INTEGER NOT NULL DEFAULT 1;
        """))
        
        # Create index on priority for efficient queue ordering queries
        # Note: We'll order by priority DESC, created_at ASC for queue processing
        log.info("[migration_033] Creating index on priority...")
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_episode_priority ON episode (priority);
        """))
        
        session.commit()
        
        log.info("[migration_033] ✅ Episode priority column added successfully")
        
    except Exception as e:
        log.error(f"[migration_033] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise

