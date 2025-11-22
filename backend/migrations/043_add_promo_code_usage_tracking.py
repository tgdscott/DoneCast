"""
Migration 043: Add Promo Code Usage Tracking

Creates promocodeusage table to track which users have used which promo codes,
preventing users from reusing the same promo code.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create promocodeusage table to track promo code usage per user"""
    
    log.info("[migration_043] Starting promo code usage tracking migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'promocodeusage' not in tables:
            log.info("[migration_043] Creating promocodeusage table...")
            session.execute(text("""
                CREATE TABLE promocodeusage (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL,
                    promo_code_id UUID NOT NULL,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context VARCHAR(50) DEFAULT 'checkout',
                    CONSTRAINT promocodeusage_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id),
                    CONSTRAINT promocodeusage_promo_code_id_fkey FOREIGN KEY (promo_code_id) REFERENCES promocode(id),
                    CONSTRAINT uq_user_promo_code UNIQUE (user_id, promo_code_id)
                )
            """))
            
            # Create indexes for fast lookups
            session.execute(text("CREATE INDEX ix_promocodeusage_user_id ON promocodeusage (user_id)"))
            session.execute(text("CREATE INDEX ix_promocodeusage_promo_code_id ON promocodeusage (promo_code_id)"))
            session.execute(text("CREATE INDEX ix_promocodeusage_used_at ON promocodeusage (used_at)"))
            
            log.info("[migration_043] ✅ Created promocodeusage table")
        else:
            log.info("[migration_043] promocodeusage table already exists, skipping...")
        
        session.commit()
        
        log.info("[migration_043] ✅ Promo code usage tracking migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_043] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise


