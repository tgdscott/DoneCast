"""
Migration 039: Add Affiliate Code Support

Creates useraffiliatecode table and adds referred_by_user_id field to user table.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create useraffiliatecode table and add referred_by_user_id to user table"""
    
    log.info("[migration_039] Starting affiliate code support migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        columns = {}
        
        # Check if user table exists and get its columns
        if 'user' in tables:
            columns = {col['name']: col for col in inspector.get_columns('user')}
        
        # Create useraffiliatecode table if it doesn't exist
        if 'useraffiliatecode' not in tables:
            log.info("[migration_039] Creating useraffiliatecode table...")
            session.execute(text("""
                CREATE TABLE useraffiliatecode (
                    id UUID PRIMARY KEY,
                    user_id UUID UNIQUE NOT NULL,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_useraffiliatecode_user_id FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE
                )
            """))
            
            # Create indexes
            session.execute(text("CREATE INDEX ix_useraffiliatecode_user_id ON useraffiliatecode (user_id)"))
            session.execute(text("CREATE INDEX ix_useraffiliatecode_code ON useraffiliatecode (code)"))
            log.info("[migration_039] ✅ Created useraffiliatecode table")
        else:
            log.info("[migration_039] useraffiliatecode table already exists, skipping...")
        
        # Add referred_by_user_id column to user table
        if 'referred_by_user_id' not in columns:
            log.info("[migration_039] Adding referred_by_user_id column to user table...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN referred_by_user_id UUID
            """))
            
            # Create index on referred_by_user_id for querying users by referrer
            session.execute(text("CREATE INDEX ix_user_referred_by_user_id ON \"user\" (referred_by_user_id)"))
            
            # Add foreign key constraint
            session.execute(text("""
                ALTER TABLE "user"
                ADD CONSTRAINT fk_user_referred_by_user_id 
                FOREIGN KEY (referred_by_user_id) REFERENCES "user"(id) ON DELETE SET NULL
            """))
            log.info("[migration_039] ✅ Added referred_by_user_id column to user table")
        else:
            log.info("[migration_039] referred_by_user_id column already exists, skipping...")
        
        session.commit()
        
        log.info("[migration_039] ✅ Affiliate code support migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_039] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise



