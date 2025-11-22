"""
Migration 042: Add Discount and Credit Fields to Promo Codes

Adds discount_percentage, bonus_credits, applies_to_monthly, and applies_to_yearly fields
to the promocode table.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add discount and credit fields to promocode table"""
    
    log.info("[migration_042] Starting promo code discount fields migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'promocode' not in tables:
            log.warning("[migration_042] promocode table does not exist, skipping...")
            return
        
        columns = {col['name']: col for col in inspector.get_columns('promocode')}
        
        # Add discount_percentage column
        if 'discount_percentage' not in columns:
            log.info("[migration_042] Adding discount_percentage column...")
            session.execute(text("""
                ALTER TABLE promocode
                ADD COLUMN discount_percentage DOUBLE PRECISION
            """))
            log.info("[migration_042] ✅ Added discount_percentage column")
        else:
            log.info("[migration_042] discount_percentage column already exists, skipping...")
        
        # Add bonus_credits column
        if 'bonus_credits' not in columns:
            log.info("[migration_042] Adding bonus_credits column...")
            session.execute(text("""
                ALTER TABLE promocode
                ADD COLUMN bonus_credits DOUBLE PRECISION
            """))
            log.info("[migration_042] ✅ Added bonus_credits column")
        else:
            log.info("[migration_042] bonus_credits column already exists, skipping...")
        
        # Add applies_to_monthly column
        if 'applies_to_monthly' not in columns:
            log.info("[migration_042] Adding applies_to_monthly column...")
            session.execute(text("""
                ALTER TABLE promocode
                ADD COLUMN applies_to_monthly BOOLEAN DEFAULT TRUE
            """))
            log.info("[migration_042] ✅ Added applies_to_monthly column")
        else:
            log.info("[migration_042] applies_to_monthly column already exists, skipping...")
        
        # Add applies_to_yearly column
        if 'applies_to_yearly' not in columns:
            log.info("[migration_042] Adding applies_to_yearly column...")
            session.execute(text("""
                ALTER TABLE promocode
                ADD COLUMN applies_to_yearly BOOLEAN DEFAULT TRUE
            """))
            log.info("[migration_042] ✅ Added applies_to_yearly column")
        else:
            log.info("[migration_042] applies_to_yearly column already exists, skipping...")
        
        session.commit()
        
        log.info("[migration_042] ✅ Promo code discount fields migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_042] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise


