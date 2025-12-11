"""
Migration 045: Add Affiliate Program Settings

Creates affiliateprogramsettings table for storing global and user-specific referral rewards.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)

def run_migration(session: Session) -> None:
    """Create affiliateprogramsettings table"""
    
    log.info("[migration_045] Starting affiliate program settings migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'affiliateprogramsettings' not in tables:
            log.info("[migration_045] Creating affiliateprogramsettings table...")
            
            # Create table
            session.execute(text("""
                CREATE TABLE affiliateprogramsettings (
                    id UUID PRIMARY KEY,
                    user_id UUID UNIQUE,
                    referrer_reward_credits FLOAT DEFAULT 0.0,
                    referee_discount_percent INTEGER DEFAULT 0,
                    referee_discount_duration VARCHAR NOT NULL DEFAULT 'once',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_affiliateprogramsettings_user_id FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE
                )
            """))
            
            # Create indexes
            session.execute(text("CREATE INDEX ix_affiliateprogramsettings_user_id ON affiliateprogramsettings (user_id)"))
            
            log.info("[migration_045] ✅ Created affiliateprogramsettings table")
        else:
            log.info("[migration_045] affiliateprogramsettings table already exists, skipping...")
            
        session.commit()
        log.info("[migration_045] ✅ Migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_045] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise
