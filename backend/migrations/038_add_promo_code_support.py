"""
Migration 038: Add Promo Code Support

Creates promocode table and adds promo_code_used field to user table.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create promocode table and add promo_code_used to user table"""
    
    log.info("[migration_038] Starting promo code support migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        columns = {}
        
        # Check if user table exists and get its columns
        if 'user' in tables:
            columns = {col['name']: col for col in inspector.get_columns('user')}
        
        # Create promocode table if it doesn't exist
        if 'promocode' not in tables:
            log.info("[migration_038] Creating promocode table...")
            session.execute(text("""
                CREATE TABLE promocode (
                    id UUID PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    description TEXT,
                    benefit_description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    usage_count INTEGER DEFAULT 0,
                    max_uses INTEGER,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR(255),
                    benefit_type VARCHAR(50),
                    benefit_value VARCHAR(255),
                    CONSTRAINT promocode_code_unique UNIQUE (code)
                )
            """))
            
            # Create index on code for fast lookups
            session.execute(text("CREATE INDEX ix_promocode_code ON promocode (code)"))
            log.info("[migration_038] ✅ Created promocode table")
        else:
            log.info("[migration_038] promocode table already exists, skipping...")
        
        # Add promo_code_used column to user table
        if 'promo_code_used' not in columns:
            log.info("[migration_038] Adding promo_code_used column to user table...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN promo_code_used VARCHAR(50)
            """))
            
            # Create index on promo_code_used for querying users by promo code
            session.execute(text("CREATE INDEX ix_user_promo_code_used ON \"user\" (promo_code_used)"))
            log.info("[migration_038] ✅ Added promo_code_used column to user table")
        else:
            log.info("[migration_038] promo_code_used column already exists, skipping...")
        
        session.commit()
        
        log.info("[migration_038] ✅ Promo code support migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_038] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise

