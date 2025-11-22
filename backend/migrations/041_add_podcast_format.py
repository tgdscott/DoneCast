"""
Migration 041: Add format field to podcast table for demographic tracking.

Adds format field to podcast table to store the format selection from onboarding.
Format values: solo, interview, cohost, panel, narrative

PostgreSQL ONLY.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add format column to podcast table (PostgreSQL ONLY)"""
    
    log.info("[migration_041] Starting podcast format column migration (PostgreSQL)...")
    
    try:
        # Check if column already exists
        bind = session.get_bind()
        inspector = inspect(bind)
        columns = [col['name'] for col in inspector.get_columns('podcast')]
        
        if 'format' in columns:
            log.info("[migration_041] Format column already exists, skipping...")
            return
        
        # Add format column as nullable VARCHAR
        log.info("[migration_041] Adding format column to podcast table...")
        session.execute(text("""
            ALTER TABLE podcast 
            ADD COLUMN format VARCHAR(50);
        """))
        
        session.commit()
        
        log.info("[migration_041] ✅ Podcast format column added successfully")
        
    except Exception as e:
        log.error(f"[migration_041] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise




